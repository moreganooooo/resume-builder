import importlib.util
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "scripts")
sys.path.insert(0, SCRIPTS)

import orchestrator  # noqa: E402

MODULE_PATH = os.path.join(SCRIPTS, "compare_eval_model.py")
spec = importlib.util.spec_from_file_location("compare_eval_model", MODULE_PATH)
bench = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(bench)


class TestReadOnlyEvaluator(unittest.TestCase):
    def test_restores_globals_and_blocks_save(self):
        old_model = orchestrator.EVAL_MODEL
        old_fallbacks = orchestrator.SCORING_FALLBACKS
        with bench._read_only_evaluator("candidate"):
            self.assertEqual(orchestrator.EVAL_MODEL, "candidate")
            self.assertEqual(orchestrator.SCORING_FALLBACKS, {})
            with self.assertRaisesRegex(RuntimeError, "persistent write"):
                bench.jd_manager.save_evaluation("a", {})
        self.assertEqual(orchestrator.EVAL_MODEL, old_model)
        self.assertIs(orchestrator.SCORING_FALLBACKS, old_fallbacks)


class TestSummary(unittest.TestCase):
    def test_uses_repeated_control_median_not_stored_baseline(self):
        report = {
            "config": {
                "control_model": "control",
                "models": ["control", "candidate"],
            },
            "attempts": [
                {"model": "control", "status": "ok", "jd_sha256": "a", "elapsed_seconds": 4, "evaluation": {"composite_score": 3.0, "recommendation": "Pursue", "role_track": "ic"}},
                {"model": "control", "status": "ok", "jd_sha256": "a", "elapsed_seconds": 6, "evaluation": {"composite_score": 4.0, "recommendation": "Pursue", "role_track": "ic"}},
                {"model": "candidate", "status": "ok", "jd_sha256": "a", "elapsed_seconds": 3, "evaluation": {"composite_score": 3.7, "recommendation": "Pursue", "role_track": "ic"}},
            ],
        }
        summary = bench._summarize(report)
        metric = summary["candidate"]["metrics"]["composite_score"]
        self.assertAlmostEqual(metric["mean_absolute_delta"], 0.2)
        self.assertEqual(summary["candidate"]["metrics"]["recommendation"]["agreement_rate"], 1.0)

    def test_failures_count_against_feasibility(self):
        report = {
            "config": {"control_model": "control", "models": ["control", "candidate"]},
            "attempts": [
                {"model": "control", "status": "ok", "jd_sha256": "a", "elapsed_seconds": 1, "evaluation": {"composite_score": 4.0}},
                {"model": "candidate", "status": "error", "jd_sha256": "a", "elapsed_seconds": None, "evaluation": None},
            ],
        }
        self.assertEqual(bench._summarize(report)["candidate"]["success_rate"], 0.0)


class TestAtomicReport(unittest.TestCase):
    def test_atomic_json_writes_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            bench._atomic_json(path, {"value": float("nan")})
            with open(path, encoding="utf-8") as fh:
                self.assertEqual(json.load(fh), {"value": None})
            self.assertFalse(os.path.exists(f"{path}.tmp"))


class TestRunOnce(unittest.TestCase):
    def test_real_entry_point_is_called_with_writes_blocked(self):
        engine = unittest.mock.Mock()
        engine.evaluate_fit.return_value = {"composite_score": 4.2}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{}")
            path = fh.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        with patch.object(orchestrator.GeminiClient, "generate", return_value=("{}", {})):
            result = bench._run_once(engine, path, "candidate", ["capability", "recruiter"])
        self.assertEqual(result["status"], "ok")
        engine.evaluate_fit.assert_called_once_with(path)


if __name__ == "__main__":
    unittest.main()
