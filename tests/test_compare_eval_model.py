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


class TestPatchAttribute(unittest.TestCase):
    def test_restores_attribute_after_success_and_failure(self):
        class Target:
            value = "original"

        with bench._patch_attribute(Target, "value", "temporary"):
            self.assertEqual(Target.value, "temporary")
        self.assertEqual(Target.value, "original")

        with self.assertRaisesRegex(RuntimeError, "boom"):
            with bench._patch_attribute(Target, "value", "temporary"):
                raise RuntimeError("boom")
        self.assertEqual(Target.value, "original")


class TestReadOnlyEvaluator(unittest.TestCase):
    def test_restores_fallbacks_and_blocks_save(self):
        old_model = orchestrator.EVAL_MODEL
        old_fallbacks = orchestrator.SCORING_FALLBACKS
        with bench._read_only_evaluator():
            self.assertEqual(orchestrator.EVAL_MODEL, old_model)
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
                {
                    "model": "control",
                    "status": "ok",
                    "jd_sha256": "a",
                    "elapsed_seconds": 4,
                    "evaluation": {
                        "composite_score": 3.0,
                        "recommendation": "Pursue",
                        "role_track": "ic",
                    },
                },
                {
                    "model": "control",
                    "status": "ok",
                    "jd_sha256": "a",
                    "elapsed_seconds": 6,
                    "evaluation": {
                        "composite_score": 4.0,
                        "recommendation": "Pursue",
                        "role_track": "ic",
                    },
                },
                {
                    "model": "candidate",
                    "status": "ok",
                    "jd_sha256": "a",
                    "elapsed_seconds": 3,
                    "evaluation": {
                        "composite_score": 3.7,
                        "recommendation": "Pursue",
                        "role_track": "ic",
                    },
                },
            ],
        }
        summary = bench._summarize(report)
        metric = summary["candidate"]["metrics"]["composite_score"]
        self.assertAlmostEqual(metric["mean_absolute_delta"], 0.2)
        self.assertEqual(
            summary["candidate"]["metrics"]["recommendation"]["agreement_rate"], 1.0
        )

    def test_failures_count_against_feasibility(self):
        report = {
            "config": {"control_model": "control", "models": ["control", "candidate"]},
            "attempts": [
                {
                    "model": "control",
                    "status": "ok",
                    "jd_sha256": "a",
                    "elapsed_seconds": 1,
                    "evaluation": {"composite_score": 4.0},
                },
                {
                    "model": "candidate",
                    "status": "error",
                    "jd_sha256": "a",
                    "elapsed_seconds": None,
                    "evaluation": None,
                },
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
    def test_real_entry_point_gets_a_sandbox_copy(self):
        engine = unittest.mock.Mock()
        engine.evaluate_fit.return_value = {"composite_score": 4.2}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{}")
            path = fh.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        source_hash = bench._sha256(path)

        result = bench._run_once(engine, path, "candidate", ["capability", "recruiter"])

        self.assertEqual(result["status"], "ok")
        sandbox_path = engine.evaluate_fit.call_args.args[0]
        self.assertNotEqual(sandbox_path, path)
        self.assertFalse(os.path.exists(sandbox_path))
        self.assertEqual(bench._sha256(path), source_hash)
        self.assertFalse(result["sandbox_changed"])

    def test_records_generate_failure_and_preserves_source(self):
        class Engine:
            def evaluate_fit(self, _path):
                orchestrator.GeminiClient.generate(
                    model=orchestrator.EVAL_MODEL,
                    system_instruction="prompt",
                    contents="context",
                )

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write("{}")
            path = fh.name
        self.addCleanup(lambda: os.path.exists(path) and os.unlink(path))
        source_hash = bench._sha256(path)

        with patch.object(
            orchestrator.GeminiClient,
            "generate",
            side_effect=ValueError("unsupported schema"),
        ):
            result = bench._run_once(Engine(), path, "candidate", ["capability"])

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_type"], "ValueError")
        self.assertEqual(result["calls"][0]["forced_model"], "candidate")
        self.assertEqual(result["calls"][0]["forced_provider"], "gemini")
        self.assertEqual(result["calls"][0]["error_type"], "ValueError")
        self.assertEqual(bench._sha256(path), source_hash)


class TestProviderRouting(unittest.TestCase):
    def test_split_candidate_preserves_publisher_model(self):
        self.assertEqual(
            bench._split_candidate("nvidia:nvidia/nemotron-3.5-lightning-30b-a3b"),
            ("nvidia", "nvidia/nemotron-3.5-lightning-30b-a3b"),
        )
        self.assertEqual(
            bench._split_candidate("gemini-3.1-flash-lite"),
            ("gemini", "gemini-3.1-flash-lite"),
        )

    def test_rejects_unknown_provider(self):
        with self.assertRaisesRegex(ValueError, "Invalid candidate"):
            bench._split_candidate("other:model")


if __name__ == "__main__":
    unittest.main()
