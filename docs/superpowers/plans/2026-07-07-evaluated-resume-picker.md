# Evaluated-Only, Scored, Sorted Resume Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "Customize Resume for a Specific JD" list only already-evaluated pending JDs, sorted best-fit first, each labeled with its score and recommendation -- backed by persisting `evaluate_fit()` results into the JD's own JSON file instead of discarding them after display.

**Architecture:** Two new `jd_manager.py` functions (`save_evaluation`/`read_evaluation`) persist and retrieve an `_evaluation` block inside each JD's JSON; a third (`read_jd_text`) becomes the single place that reads a JD file for prompt use, stripping that block out so it never leaks into a later Gemini call. The two existing evaluation entry points call `save_evaluation` on success; a new `picker.pick_one_evaluated_jd()` reads it back to build the picker.

**Tech Stack:** Python 3.10+, stdlib `unittest` + `unittest.mock`.

## Global Constraints

- Python 3.10+ syntax, matching the rest of `scripts/`.
- No changes to `evaluate_fit()`'s signature, return shape, or its
  documented "no files written" contract for a *failed* evaluation -- only
  successful results get persisted, and only by the caller, not inside
  `evaluate_fit()` itself.
- No changes to the cover-letter picker (`_handle_coverletter_one`,
  `pick_one_pending_jd`) -- both stay exactly as they are.
- No staleness detection, no expiry, no re-evaluation triggers -- a stored
  `_evaluation` is valid until something overwrites it.
- Tests: stdlib `unittest`, `tests/test_*.py` naming (auto-discovered),
  `sys.path.insert(0, SCRIPTS_DIR)` + plain `import <module>`, matching
  every existing test file in this repo.
- Run the suite with `python -m unittest discover -s tests -v` from the
  project root with `.venv/` activated (or `resume test -v`).

---

### Task 1: `save_evaluation()` + `read_evaluation()`

**Files:**
- Modify: `scripts/jd_manager.py`
- Test: `tests/test_jd_manager.py`

**Interfaces:**
- Produces: `save_evaluation(jd_path: str, evaluation: dict) -> None`,
  `read_evaluation(jd_path: str) -> dict | None`. Used by Task 3 (the two
  evaluation entry points) and Task 4 (the new picker).

- [ ] **Step 1: Write the failing tests**

In `tests/test_jd_manager.py`, find the trailing block at the end of the
file:

```python
if __name__ == "__main__":
    unittest.main()
```

Replace it with the new test class plus the same trailing block moved
after it (so there's still exactly one `if __name__` block, now at the
true end of the file):

```python
class TestSaveAndReadEvaluation(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_evaluation")
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

    def test_save_then_read_round_trips_score_and_recommendation(self):
        path = self._write("a.json", json.dumps({"job_title": "Role", "company_name": "Acme"}))
        jd_manager.save_evaluation(path, {
            "composite_score": 4.2, "recommendation": "Strong pursue", "hard_blockers": [],
        })
        result = jd_manager.read_evaluation(path)
        self.assertEqual(result["composite_score"], 4.2)
        self.assertEqual(result["recommendation"], "Strong pursue")
        self.assertIn("evaluated_at", result)

    def test_save_preserves_the_rest_of_the_jd_content(self):
        path = self._write("a.json", json.dumps({"job_title": "Role", "company_name": "Acme"}))
        jd_manager.save_evaluation(path, {"composite_score": 3.0, "recommendation": "Selective pursue"})
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["job_title"], "Role")
        self.assertEqual(data["company_name"], "Acme")

    def test_save_on_plain_text_jd_does_not_raise_and_leaves_file_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting, not JSON.")
        jd_manager.save_evaluation(path, {"composite_score": 4.0, "recommendation": "Strong pursue"})
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "Just a plain text job posting, not JSON.")

    def test_read_evaluation_returns_none_when_never_evaluated(self):
        path = self._write("a.json", json.dumps({"job_title": "Role"}))
        self.assertIsNone(jd_manager.read_evaluation(path))

    def test_read_evaluation_returns_none_for_plain_text_jd(self):
        path = self._write("dummy.txt", "Just plain text.")
        self.assertIsNone(jd_manager.read_evaluation(path))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_jd_manager.TestSaveAndReadEvaluation -v`
Expected: FAIL -- `AttributeError: module 'jd_manager' has no attribute 'save_evaluation'`.

- [ ] **Step 3: Add `save_evaluation()` and `read_evaluation()` to `scripts/jd_manager.py`**

Add them right after `extract_job_meta()`:

```python
def save_evaluation(jd_path: str, evaluation: dict) -> None:
    """Persists an evaluate_fit() result into the JD's own JSON file under
    an _evaluation key, so a later picker can filter/sort/label by it
    without re-running the (real, costly) Gemini evaluation call. No-ops
    silently for non-JSON-dict JDs (e.g. plain-text fixtures) -- they
    simply never become eligible for the evaluated-only picker."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return
    if not isinstance(data, dict):
        return

    data["_evaluation"] = {
        "composite_score": evaluation.get("composite_score"),
        "recommendation": evaluation.get("recommendation"),
        "hard_blockers": evaluation.get("hard_blockers") or [],
        "evaluated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    with open(jd_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def read_evaluation(jd_path: str) -> dict | None:
    """Reads back a persisted _evaluation (see save_evaluation()), or None
    if the JD isn't a JSON dict or has never been evaluated."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data.get("_evaluation")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_jd_manager.TestSaveAndReadEvaluation -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test).

- [ ] **Step 6: Commit**

```bash
git add scripts/jd_manager.py tests/test_jd_manager.py
git commit -m "feat: persist evaluate_fit results into the JD's own JSON file"
```

---

### Task 2: `read_jd_text()` -- keep evaluation metadata out of Gemini prompts

**Files:**
- Modify: `scripts/jd_manager.py`
- Modify: `scripts/orchestrator.py` (3 call sites: `evaluate_fit`,
  `build_tailored_coverletter`, `build_tailored_resume`)
- Test: `tests/test_jd_manager.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `read_jd_text(jd_path: str) -> str` (raises `FileNotFoundError`
  like a raw `open()` would). Used directly by `orchestrator.py`'s three
  call sites in this task -- no other task depends on it.

- [ ] **Step 1: Write the failing tests**

In `tests/test_jd_manager.py`, find the trailing block Task 1 left at the
end of the file:

```python
if __name__ == "__main__":
    unittest.main()
```

Replace it with the new test class plus the same trailing block moved
after it:

```python
class TestReadJdText(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(__file__), "_tmp_read_jd_text")
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

    def test_jd_without_evaluation_returns_raw_text_unchanged(self):
        raw = json.dumps({"job_title": "Role", "company_name": "Acme"})
        path = self._write("a.json", raw)
        self.assertEqual(jd_manager.read_jd_text(path), raw)

    def test_jd_with_evaluation_strips_only_that_key(self):
        path = self._write("a.json", json.dumps({
            "job_title": "Role", "company_name": "Acme",
            "_evaluation": {"composite_score": 4.0, "recommendation": "Strong pursue"},
        }))
        result = jd_manager.read_jd_text(path)
        parsed = json.loads(result)
        self.assertNotIn("_evaluation", parsed)
        self.assertEqual(parsed["job_title"], "Role")
        self.assertEqual(parsed["company_name"], "Acme")

    def test_plain_text_jd_returns_raw_text_unchanged(self):
        path = self._write("dummy.txt", "Just a plain text job posting.")
        self.assertEqual(jd_manager.read_jd_text(path), "Just a plain text job posting.")

    def test_missing_file_raises_file_not_found_error(self):
        with self.assertRaises(FileNotFoundError):
            jd_manager.read_jd_text(os.path.join(self.tmp_dir, "does_not_exist.json"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_jd_manager.TestReadJdText -v`
Expected: FAIL -- `AttributeError: module 'jd_manager' has no attribute 'read_jd_text'`.

- [ ] **Step 3: Add `read_jd_text()` to `scripts/jd_manager.py`**

Add it right after `read_evaluation()`:

```python
def read_jd_text(jd_path: str) -> str:
    """Reads a JD file's content for prompt use, stripping the persisted
    _evaluation key (see save_evaluation()) if present so a prior
    evaluation's score/recommendation never leaks into a Gemini prompt as
    if it were job-description content. Passes plain-text (or otherwise
    non-JSON-dict) JDs through unchanged. Raises FileNotFoundError exactly
    like a raw open() would, so existing call-site error handling needs no
    changes."""
    with open(jd_path, "r", encoding="utf-8") as f:
        raw_text = f.read()
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    if isinstance(data, dict) and "_evaluation" in data:
        data = {k: v for k, v in data.items() if k != "_evaluation"}
        return json.dumps(data, indent=2)
    return raw_text
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_jd_manager.TestReadJdText -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Wire it into the three `orchestrator.py` call sites**

In `evaluate_fit()`, find:
```python
        try:
            with open(jd_path, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        eval_prompt = self.load_prompt("evaluate_fit.md")
```
Replace with:
```python
        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        eval_prompt = self.load_prompt("evaluate_fit.md")
```

In `build_tailored_coverletter()`, find:
```python
        try:
            with open(jd_path, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        jd_data = _parse_jd_data(jd_text)
```
Replace with:
```python
        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        jd_data = _parse_jd_data(jd_text)
```

In `build_tailored_resume()`, find:
```python
        try:
            with open(jd_path, "r", encoding="utf-8") as f:
                jd_text = f.read()
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        situational_candidates = situational_roles.detect_situational_candidates(jd_text)
```
Replace with:
```python
        try:
            jd_text = jd_manager.read_jd_text(jd_path)
        except FileNotFoundError:
            print(f"  ERROR: JD file not found: {jd_path}")
            return {}

        situational_candidates = situational_roles.detect_situational_candidates(jd_text)
```

- [ ] **Step 6: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test -- these three call sites' existing tests all
use JD fixtures without an `_evaluation` key, so `read_jd_text()` returns
their content completely unchanged and none of them observe any
difference).

- [ ] **Step 7: Commit**

```bash
git add scripts/jd_manager.py scripts/orchestrator.py tests/test_jd_manager.py
git commit -m "feat: strip persisted evaluation metadata out of JD text before it reaches a Gemini prompt"
```

---

### Task 3: Wire persistence into both evaluation entry points

**Files:**
- Modify: `scripts/batch_evaluate.py`
- Modify: `scripts/menu.py`
- Test: `tests/test_batch_evaluate.py`, `tests/test_menu.py`

**Interfaces:**
- Consumes: `jd_manager.save_evaluation(jd_path, evaluation)` from Task 1.

- [ ] **Step 1: Write the failing test for `batch_evaluate.evaluate_all_pending()`**

Add `from unittest.mock import patch` to `tests/test_batch_evaluate.py`'s
imports (it currently has none), then append a new class:

```python
class TestEvaluateAllPendingPersistsEvaluations(unittest.TestCase):

    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_successful_evaluation_gets_persisted(self, mock_engine_cls, mock_key, mock_meta, mock_save):
        mock_engine_cls.return_value.evaluate_fit.return_value = {
            "composite_score": 4.0, "recommendation": "Strong pursue", "hard_blockers": [],
        }
        batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_save.assert_called_once_with("jds/a.json", {
            "composite_score": 4.0, "recommendation": "Strong pursue", "hard_blockers": [],
        })

    @patch("batch_evaluate.jd_manager.save_evaluation")
    @patch("batch_evaluate.jd_manager.extract_job_meta", return_value=("Role", "Acme"))
    @patch("batch_evaluate.jd_manager.compute_job_key", return_value="key1")
    @patch("batch_evaluate.orchestrator.ResumeEngine")
    def test_errored_evaluation_is_not_persisted(self, mock_engine_cls, mock_key, mock_meta, mock_save):
        mock_engine_cls.return_value.evaluate_fit.return_value = {}
        batch_evaluate.evaluate_all_pending(["jds/a.json"])
        mock_save.assert_not_called()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_batch_evaluate.TestEvaluateAllPendingPersistsEvaluations -v`
Expected: FAIL -- the first test's `mock_save.assert_called_once_with(...)`
fails because nothing calls `save_evaluation` yet.

- [ ] **Step 3: Wire `save_evaluation()` into `evaluate_all_pending()`**

In `scripts/batch_evaluate.py`, find:
```python
        if not evaluation:
            results.append({
                "job_key": jd_manager.compute_job_key(path),
                "source_file": path,
                "company_name": company_name or "unknown",
                "job_title": job_title or "unknown",
                "composite_score": None,
                "recommendation": None,
                "hard_blockers": [],
                "error": True,
            })
            continue

        results.append({
```
Replace with:
```python
        if not evaluation:
            results.append({
                "job_key": jd_manager.compute_job_key(path),
                "source_file": path,
                "company_name": company_name or "unknown",
                "job_title": job_title or "unknown",
                "composite_score": None,
                "recommendation": None,
                "hard_blockers": [],
                "error": True,
            })
            continue

        jd_manager.save_evaluation(path, evaluation)

        results.append({
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m unittest tests.test_batch_evaluate.TestEvaluateAllPendingPersistsEvaluations -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Write the failing test for `menu._handle_evaluate_one()`**

Append to `tests/test_menu.py`'s `TestHandleEvaluateOne` class (after
`test_returns_true_when_result_truthy`):

```python
    @patch("menu.jd_manager.save_evaluation")
    @patch("menu.orchestrator.ResumeEngine")
    @patch("menu.questionary.path")
    def test_persists_evaluation_on_success(self, mock_path, mock_engine_cls, mock_save):
        mock_path.return_value.ask.return_value = "jds/a.json"
        result = {"archetype": "x", "composite_score": 4.0, "recommendation": "Strong pursue"}
        mock_engine_cls.return_value.evaluate_fit.return_value = result
        menu._handle_evaluate_one()
        mock_save.assert_called_once_with("jds/a.json", result)
```

- [ ] **Step 6: Run the test to verify it fails**

Run: `python -m unittest tests.test_menu.TestHandleEvaluateOne.test_persists_evaluation_on_success -v`
Expected: FAIL -- `mock_save.assert_called_once_with(...)` fails, nothing
calls it yet.

- [ ] **Step 7: Wire `save_evaluation()` into `_handle_evaluate_one()`**

In `scripts/menu.py`, find:
```python
def _handle_evaluate_one() -> bool:
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return False
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(path)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        return False
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
```
Replace with:
```python
def _handle_evaluate_one() -> bool:
    path = questionary.path("Path to the JD file:", style=cli_art.QUESTIONARY_STYLE).ask()
    if not path:
        return False
    engine = orchestrator.ResumeEngine()
    result = engine.evaluate_fit(path)
    if not result:
        cli_art.console.print(f"{cli_art.ERROR} Evaluation failed -- no parseable result.")
        return False
    jd_manager.save_evaluation(path, result)
    cli_art.console.print(f"\n[bold]Archetype:[/bold] {result.get('archetype', 'unknown')}")
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `python -m unittest tests.test_menu.TestHandleEvaluateOne -v`
Expected: PASS (3 tests).

- [ ] **Step 9: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test).

- [ ] **Step 10: Commit**

```bash
git add scripts/batch_evaluate.py scripts/menu.py tests/test_batch_evaluate.py tests/test_menu.py
git commit -m "feat: persist evaluation results from both evaluation entry points"
```

---

### Task 4: `picker.pick_one_evaluated_jd()` + wire into `_handle_tailor_one()`

**Files:**
- Modify: `scripts/picker.py`
- Modify: `scripts/menu.py`
- Test: `tests/test_picker.py`, `tests/test_menu.py`

**Interfaces:**
- Consumes: `jd_manager.read_evaluation(jd_path)` from Task 1,
  `jd_manager.extract_job_meta(jd_path)` (existing).
- Produces: `pick_one_evaluated_jd(pending_paths: list) -> str | None`.
  Used by `menu._handle_tailor_one()`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_picker.py`:

```python
class TestPickOneEvaluatedJd(unittest.TestCase):

    def test_empty_list_returns_none_without_prompting(self):
        with patch("picker.questionary.select") as mock_select:
            result = picker.pick_one_evaluated_jd([])
        self.assertIsNone(result)
        mock_select.assert_not_called()

    @patch("picker.jd_manager.read_evaluation", return_value=None)
    def test_no_evaluated_jds_prints_hint_and_returns_none(self, mock_read):
        with patch("picker.questionary.select") as mock_select, \
             patch("picker.cli_art.console.print") as mock_print:
            result = picker.pick_one_evaluated_jd(["jds/a.json"])
        self.assertIsNone(result)
        mock_select.assert_not_called()
        printed = mock_print.call_args[0][0]
        self.assertIn("Hint", printed)

    @patch("picker.jd_manager.extract_job_meta")
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.questionary.select")
    def test_excludes_jds_with_no_evaluation(self, mock_select, mock_read, mock_meta):
        mock_read.side_effect = lambda path: {
            "jds/a.json": {"composite_score": 4.0, "recommendation": "Strong pursue"},
            "jds/b.json": None,
        }[path]
        mock_meta.return_value = ("Role", "Acme")
        mock_select.return_value.ask.return_value = "jds/a.json"

        picker.pick_one_evaluated_jd(["jds/a.json", "jds/b.json"])

        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(len(choices), 1)
        self.assertEqual(choices[0].value, "jds/a.json")

    @patch("picker.jd_manager.extract_job_meta")
    @patch("picker.jd_manager.read_evaluation")
    @patch("picker.questionary.select")
    def test_sorts_best_score_first_regardless_of_input_order(self, mock_select, mock_read, mock_meta):
        mock_read.side_effect = lambda path: {
            "jds/low.json": {"composite_score": 2.5, "recommendation": "Low-priority pursue"},
            "jds/high.json": {"composite_score": 4.8, "recommendation": "Strong pursue"},
        }[path]
        mock_meta.return_value = ("Role", "Company")
        mock_select.return_value.ask.return_value = "jds/high.json"

        picker.pick_one_evaluated_jd(["jds/low.json", "jds/high.json"])

        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].value, "jds/high.json")
        self.assertEqual(choices[1].value, "jds/low.json")

    @patch("picker.jd_manager.extract_job_meta", return_value=("Content Strategist", "Acme"))
    @patch("picker.jd_manager.read_evaluation", return_value={
        "composite_score": 4.8, "recommendation": "Strong pursue",
    })
    @patch("picker.questionary.select")
    def test_label_includes_score_and_recommendation(self, mock_select, mock_read, mock_meta):
        mock_select.return_value.ask.return_value = "jds/a.json"
        picker.pick_one_evaluated_jd(["jds/a.json"])
        choices = mock_select.call_args.kwargs["choices"]
        self.assertEqual(choices[0].title, "4.8/5 | Strong pursue | Acme | Content Strategist")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m unittest tests.test_picker.TestPickOneEvaluatedJd -v`
Expected: FAIL -- `AttributeError: module 'picker' has no attribute 'pick_one_evaluated_jd'`.

- [ ] **Step 3: Add `pick_one_evaluated_jd()` to `scripts/picker.py`**

Add it at the end of the file, after `pick_one_pending_jd()`:

```python
def pick_one_evaluated_jd(pending_paths: list) -> str | None:
    """Single-choice picker restricted to pending JDs carrying a persisted
    _evaluation (jd_manager.save_evaluation(), written by a prior
    "Evaluate" run) -- sorted best composite_score first, each choice
    labeled with its score/recommendation. A JD with no _evaluation simply
    isn't eligible; it needs to be evaluated first."""
    evaluated = []
    for path in pending_paths:
        evaluation = jd_manager.read_evaluation(path)
        if not evaluation:
            continue
        title, company = jd_manager.extract_job_meta(path)
        evaluated.append((evaluation, path, title, company))

    if not evaluated:
        cli_art.console.print(
            "Nothing to pick from -- no evaluated JDs yet.\n"
            "Hint: Don't see the role you're expecting? Run an evaluation "
            "on it first (Evaluate ALL Pending JDs or Evaluate a Specific "
            "JD) -- then it'll appear in this list."
        )
        return None

    evaluated.sort(key=lambda item: -(item[0].get("composite_score") or 0))

    choices = [
        questionary.Choice(
            title=(
                f"{evaluation.get('composite_score')}/5 | {evaluation.get('recommendation')} | "
                f"{company or '?'} | {title or os.path.basename(path)}"
            ),
            value=path,
        )
        for evaluation, path, title, company in evaluated
    ]
    return questionary.select(
        "Which JD?", choices=choices, style=cli_art.QUESTIONARY_STYLE,
    ).ask()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m unittest tests.test_picker.TestPickOneEvaluatedJd -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Wire it into `menu._handle_tailor_one()`**

Find:
```python
def _handle_tailor_one() -> bool:
    path = picker.pick_one_pending_jd(jd_manager.get_pending_jds())
    if not path:
        return False
    completed, _failed = orchestrator.run_pipeline(jd_path=path)
    return completed > 0
```
Replace with:
```python
def _handle_tailor_one() -> bool:
    path = picker.pick_one_evaluated_jd(jd_manager.get_pending_jds())
    if not path:
        return False
    completed, _failed = orchestrator.run_pipeline(jd_path=path)
    return completed > 0
```

- [ ] **Step 6: Update `TestHandleTailorOne`'s existing patch targets**

In `tests/test_menu.py`, find:
```python
class TestHandleTailorOne(unittest.TestCase):

    @patch("menu.picker.pick_one_pending_jd", return_value=None)
    def test_returns_false_when_no_path_picked(self, mock_pick):
        self.assertFalse(menu._handle_tailor_one())

    @patch("menu.orchestrator.run_pipeline", return_value=(1, 0))
    @patch("menu.picker.pick_one_pending_jd", return_value="jds/a.json")
    def test_returns_true_when_completed(self, mock_pick, mock_run):
        self.assertTrue(menu._handle_tailor_one())
        mock_run.assert_called_once_with(jd_path="jds/a.json")
```
Replace with:
```python
class TestHandleTailorOne(unittest.TestCase):

    @patch("menu.picker.pick_one_evaluated_jd", return_value=None)
    def test_returns_false_when_no_path_picked(self, mock_pick):
        self.assertFalse(menu._handle_tailor_one())

    @patch("menu.orchestrator.run_pipeline", return_value=(1, 0))
    @patch("menu.picker.pick_one_evaluated_jd", return_value="jds/a.json")
    def test_returns_true_when_completed(self, mock_pick, mock_run):
        self.assertTrue(menu._handle_tailor_one())
        mock_run.assert_called_once_with(jd_path="jds/a.json")
```

(Leave `TestHandleCoverletterOne` untouched -- it still uses
`pick_one_pending_jd`, which is unaffected by this change.)

- [ ] **Step 7: Run the full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test).

- [ ] **Step 8: Commit**

```bash
git add scripts/picker.py scripts/menu.py tests/test_picker.py tests/test_menu.py
git commit -m "feat: restrict the resume picker to evaluated JDs, sorted and scored"
```

---

### Task 5: Full-suite confirmation + live verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full test suite one more time**

Run: `python -m unittest discover -s tests -v`
Expected: PASS (every test, all four prior tasks combined).

- [ ] **Step 2: Live-verify the empty-state hint**

Run `resume`, choose "Customize Resume for a Specific JD" before
evaluating anything (or against a fresh pending JD). Confirm the hint
message prints and no picker appears.

- [ ] **Step 3: Live-verify evaluation persistence and the picker**

Run "Evaluate a Specific JD" (or "Evaluate ALL Pending JDs") against 2-3
real pending JDs. Then open the JD file(s) directly and confirm each now
has an `_evaluation` key with `composite_score`/`recommendation`/
`evaluated_at`. Then choose "Customize Resume for a Specific JD" and
confirm:
1. Only those evaluated JDs appear -- nothing else from the ~150+ other
   pending JDs.
2. They're ordered best `composite_score` first.
3. Each choice's label shows its score and recommendation alongside
   company/title.

- [ ] **Step 4: Live-verify the prompt-leak fix**

Pick one of the evaluated JDs from Step 3 and run a real tailor against
it (or at minimum re-run "Evaluate a Specific JD" on the same file a
second time). Confirm nothing looks off in Step 1's extracted keywords --
there should be no trace of the `_evaluation` block (score numbers,
"Strong pursue", etc.) surfacing anywhere in the keyword-extraction output
or resume content.

- [ ] **Step 5: Report back**

No commit for this task -- it's verification only. If any live check
surfaces a real problem, stop and report it rather than declaring the
feature done.

---

## Self-Review Notes

- **Spec coverage:** Goal 1 (evaluated-only) + Goal 4 (hint) -> Task 4.
  Goal 2 (sorted) -> Task 4. Goal 3 (score shown) -> Task 4. Goal 5
  (persist without re-evaluating) -> Tasks 1 and 3. The prompt-leak fix
  from the spec's Architecture section 2 -> Task 2. All spec goals and
  the one non-obvious architectural requirement have a task.
- **Placeholder scan:** No TBD/TODO markers; every step has complete,
  runnable code or an exact command.
- **Type consistency:** `save_evaluation(jd_path: str, evaluation: dict) -> None`
  and `read_evaluation(jd_path: str) -> dict | None` (Task 1) are used
  identically in Task 3 (evaluation entry points) and Task 4 (picker) --
  no signature drift. `read_jd_text(jd_path: str) -> str` (Task 2) is
  self-contained to its three call sites, used nowhere else.
  `pick_one_evaluated_jd(pending_paths: list) -> str | None` (Task 4)
  matches `pick_one_pending_jd`'s existing signature shape exactly, so
  `menu._handle_tailor_one()`'s call site swap is a one-line change.
- **Scope check confirmed against Non-Goals:** no changes to
  `pick_and_process()`, `pick_one_pending_jd()`,
  `_handle_coverletter_one()`, or `evaluate_fit()`'s own signature/return
  contract -- verified none of Tasks 1-4 touch those.
