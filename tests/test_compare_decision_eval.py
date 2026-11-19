import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import compare_decision_eval as bench  # noqa: E402
import orchestrator  # noqa: E402


def _score_answer(level):
    return {
        "type": "score",
        "score": level - 1.01,
        "probabilities": {
            str(i): (0.99 if i == level - 1 else 0.0025) for i in range(5)
        },
    }


class TestDecisionsBenchmark(unittest.TestCase):
    def setUp(self):
        self.engine = object.__new__(orchestrator.ResumeEngine)
        self.engine.prompts_dir = str(ROOT / "resume-engine" / "prompts")
        self.questions, self.policy = bench._questions(self.engine)

    def test_production_prompts_supply_all_rubrics(self):
        self.assertEqual(len(self.questions), 21)
        self.assertEqual(sum(q["type"] == "score" for q in self.questions.values()), 18)
        levels = self.questions["remote_quality"]["criteria"]
        self.assertEqual(len(levels), 5)
        self.assertEqual(levels[4], "fully remote and workable")
        self.assertIn("Master's plus 3 years", self.policy)
        self.assertIn("career_gap:", self.questions["narrative_burden"]["instructions"])

    def test_revised_prompts_distinguish_scope_and_eligibility(self):
        revised = bench._revised_questions(self.questions)
        self.assertEqual(len(revised), 25)
        self.assertEqual(
            set(bench.REVISED_RUBRICS),
            {
                key
                for key, question in self.questions.items()
                if question["type"] == "score"
            },
        )
        for key in bench.REVISED_RUBRICS:
            self.assertEqual(len(set(revised[key]["criteria"])), 5)
        self.assertIn("central", revised["field_domain_scope"]["criteria"])
        self.assertNotIn("central", revised["degree_scope"]["criteria"])
        self.assertIn(
            "geographic restrictions", revised["remote_eligibility"]["instructions"]
        )
        self.assertIn("career_gap:", revised["narrative_burden"]["instructions"])

    def test_choice_threshold_sends_plurality_to_review(self):
        answers = {"years_experience": {"choice": "flagged", "confidence": 0.451}}
        self.assertEqual(
            bench._choice(answers, "years_experience", bench.CHOICES, 0), "flagged"
        )
        self.assertEqual(
            bench._choice(answers, "years_experience", bench.CHOICES, 0.5), "unclear"
        )
        self.assertEqual(
            bench._scoped_flag("optional_or_absent", "flagged"), "not_flagged"
        )
        self.assertEqual(bench._scoped_flag("unclear", "flagged"), "unclear")
        self.assertEqual(bench._scoped_flag("central", "flagged"), "flagged")

    @patch.object(
        bench.gemini_client,
        "_get_auth_headers",
        return_value={"x-goog-api-key": "fictional"},
    )
    @patch.object(bench.requests, "post")
    def test_rest_payload_and_missing_answer(self, post, auth_headers):
        questions = {"remote_quality": self.questions["remote_quality"]}
        answer = _score_answer(5)
        post.return_value.json.return_value = {"answers": {"remote_quality": answer}}
        self.assertEqual(
            bench._request_decisions("posting", questions, self.policy)["answers"][
                "remote_quality"
            ],
            answer,
        )
        auth_headers.assert_called_once_with("gemini-decision-1")
        self.assertEqual(
            post.call_args.args,
            ("https://generativelanguage.googleapis.com/v1beta/decisions",),
        )
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["model"], "gemini-decision-1")
        self.assertEqual(body["questions"], questions)
        self.assertTrue(body["input"].endswith("posting"))
        post.return_value.json.return_value = {"answers": {}}
        with self.assertRaisesRegex(ValueError, "remote_quality"):
            bench._request_decisions("posting", questions, self.policy)

    def test_replays_production_with_only_numeric_subscores_replaced(self):
        fit, interview, practical = (
            dict.fromkeys(fields, 5) for fields in bench.GROUPS.values()
        )
        raw_blocker = {"category": "degree", "text": "Master's degree required"}
        stage_responses = {
            orchestrator.CapabilityEvaluationSchema: {"fit_subscores": fit},
            orchestrator.RecruiterEvaluationSchema: {
                "interview_odds_subscores": interview,
                "practical_pursue_subscores": practical,
                "hard_blockers": [raw_blocker],
            },
        }
        answers = {
            name: (
                _score_answer(5 if name == "remote_quality" else 4)
                if spec["type"] == "score"
                else {"type": "choice", "choice": "not_flagged"}
            )
            for name, spec in self.questions.items()
        }

        def generate(**kwargs):
            self.assertEqual(kwargs["contents"], "same fit context")
            self.assertFalse(kwargs["model_fallback"])
            return json.dumps(stage_responses[kwargs["response_schema"]]), {}

        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "job.json"
            path.write_text(
                '{"job_title":"Example","work_model":"Remote","skills":[{"skill":"Planning"}]}',
                encoding="utf-8",
            )
            original = path.read_bytes()
            self.engine.kb_dir = scratch
            with (
                patch.object(
                    self.engine,
                    "load_yaml",
                    return_value={"location": {"remote_required": True}},
                ),
                patch.object(
                    self.engine,
                    "build_fit_evaluation_context",
                    return_value="same fit context",
                ),
                patch.object(
                    orchestrator, "_resolve_commute_distance", return_value=None
                ),
                patch.object(
                    orchestrator.GeminiClient, "generate", side_effect=generate
                ) as generation,
                patch.object(
                    bench, "_request_decisions", return_value={"answers": answers}
                ) as decisions,
            ):
                pair = bench._run_pair(
                    self.engine,
                    path,
                    self.questions,
                    self.policy,
                    datetime.now(timezone.utc),
                )
            self.assertEqual(path.read_bytes(), original)
        self.assertEqual(generation.call_count, 2)
        decisions.assert_called_once_with(
            "same fit context", self.questions, self.policy
        )
        self.assertEqual(pair["control_scores"]["fit_score"], 5)
        self.assertEqual(pair["decision_scores"]["fit_score"], 4)
        self.assertGreater(pair["decision_scores"]["composite_score"], 0)
        self.assertEqual(pair["control_blockers"]["years_or_degree"], "flagged")
        self.assertEqual(pair["decision_blockers"]["years_or_degree"], "not_flagged")

    def test_ab_pair_reuses_control_and_keeps_remote_quality_fixed_in_revised_composite(
        self,
    ):
        raw = {
            group: dict.fromkeys(weights, 5) for group, weights in bench.GROUPS.items()
        }
        raw.update(
            {"hard_blockers": [], "recommendation": "Pursue", "prestige_tier": "Tier-2"}
        )
        stage_responses = {
            orchestrator.CapabilityEvaluationSchema: {
                "fit_subscores": raw["fit_subscores"]
            },
            orchestrator.RecruiterEvaluationSchema: {
                key: raw[key]
                for key in (
                    "interview_odds_subscores",
                    "practical_pursue_subscores",
                    "hard_blockers",
                    "recommendation",
                    "prestige_tier",
                )
            },
        }

        def generate(**kwargs):
            return json.dumps(stage_responses[kwargs["response_schema"]]), {}

        def decide(context, questions, policy):
            self.assertIn("same fit context", context)
            revised = "remote_eligibility" in questions
            self.assertEqual("New York" in context, revised)
            answers = {
                name: (
                    _score_answer(4)
                    if spec["type"] == "score"
                    else {"choice": next(iter(spec["criteria"])), "confidence": 0.9}
                )
                for name, spec in questions.items()
            }
            answers["years_experience"] = {"choice": "flagged", "confidence": 0.45}
            if revised:
                answers["degree_scope"] = {
                    "choice": "optional_or_absent",
                    "confidence": 0.9,
                }
            return {"answers": answers}

        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "job.json"
            path.write_text(
                '{"job_title":"Example","work_model":"Remote","skills":[{"skill":"Planning"}]}',
                encoding="utf-8",
            )
            self.engine.kb_dir = scratch
            with (
                patch.object(
                    self.engine,
                    "load_yaml",
                    return_value={"location": {"remote_required": True}},
                ),
                patch.object(
                    self.engine,
                    "build_fit_evaluation_context",
                    return_value="same fit context",
                ),
                patch.object(
                    orchestrator, "_resolve_commute_distance", return_value=None
                ),
                patch.object(
                    orchestrator.GeminiClient, "generate", side_effect=generate
                ) as generation,
                patch.object(
                    bench, "_request_decisions", side_effect=decide
                ) as decisions,
            ):
                pair = bench._run_pair(
                    self.engine,
                    path,
                    self.questions,
                    self.policy,
                    datetime.now(timezone.utc),
                    variant="both",
                    facts='{"work_state":"New York"}',
                )
        self.assertEqual(generation.call_count, 2)
        self.assertEqual(decisions.call_count, 2)
        self.assertEqual(pair["decision_scores"]["composite_score"], 0)
        revised = pair["revised"]
        self.assertGreater(revised["decision_scores"]["composite_score"], 0)
        self.assertEqual(revised["decision_blockers"]["years_or_degree"], "unclear")
        self.assertEqual(revised["remote_eligibility"], "eligible")

    def test_rank_reversals_and_false_blockers_use_paired_rows(self):
        def pair(job_id, control, decision, label, before, after):
            return {
                "id": job_id,
                "name": job_id,
                "control_scores": dict.fromkeys(bench.METRICS, control),
                "decision_scores": dict.fromkeys(bench.METRICS, decision),
                "label": label,
                "control_blockers": {"years_or_degree": before},
                "decision_blockers": {"years_or_degree": after},
            }

        report = bench._summary(
            {
                "a": pair("a", 4, 3, "does_not_block", "flagged", "not_flagged"),
                "b": pair("b", 3, 4, "blocks", "flagged", "unclear"),
                "c": {"error": "quota"},
            }
        )
        self.assertEqual(report["paired_jobs"], 2)
        self.assertEqual(report["rankings"]["composite_score"]["reversed"], 1)
        blockers = report["blockers"]["years_or_degree"]
        self.assertEqual(blockers["control"]["false_positives"], ["a"])
        self.assertEqual(blockers["decision"]["false_positives"], [])
        self.assertEqual(blockers["decision"]["false_negatives"], ["b"])
        self.assertEqual(blockers["decision"]["abstentions"], 1)

    def test_overqualification_does_not_count_as_a_blocker(self):
        entries = [{"category": "years_experience", "direction": "over_qualified"}]
        self.assertEqual(
            bench._control_flags(entries)["years_or_degree"], "not_flagged"
        )

    def test_cli_reads_holdout_snapshot_and_resumes_completed_posting(self):
        def evaluate(engine, path, questions, policy, as_of):
            self.assertEqual(path.read_text(encoding="utf-8"), "Preserved posting")
            return {
                "control_scores": dict.fromkeys(bench.METRICS, 4),
                "decision_scores": dict.fromkeys(bench.METRICS, 3),
                "control_blockers": {
                    "years_or_degree": "flagged",
                    "field_domain": "not_flagged",
                },
                "decision_blockers": {
                    "years_or_degree": "not_flagged",
                    "field_domain": "not_flagged",
                },
            }

        with tempfile.TemporaryDirectory() as scratch:
            root = Path(scratch)
            labels, sources, output = (
                root / name for name in ("labels.csv", "posts.json", "report.json")
            )
            labels.write_text(
                "job_id,title,company,stratum,label,field_domain_label\n"
                "one,Role,Example,neither,does_not_block,n/a\n",
                encoding="utf-8",
            )
            sources.write_text(
                '{"one":{"raw_text":"Preserved posting"}}', encoding="utf-8"
            )
            args = ["--profile", "morgan", "--holdout", "--output", str(output)]
            with (
                patch.object(bench.profile_paths, "set_active_profile"),
                patch.object(
                    bench.blockers,
                    "_holdout_paths",
                    return_value=(str(labels), str(sources)),
                ),
                patch.object(
                    bench.gemini_client, "api_keys", return_value=["fictional"]
                ),
                patch.object(orchestrator, "ResumeEngine", return_value=self.engine),
                patch.object(bench, "_run_pair", side_effect=evaluate) as run,
                patch("builtins.print"),
            ):
                self.assertEqual(bench.main(args), 0)
                first_report = output.read_bytes()
                self.assertEqual(bench.main([*args, "--resume"]), 0)
                run.assert_called_once()
                self.assertEqual(output.read_bytes(), first_report)

        summary = json.loads(first_report)["summary"]
        self.assertEqual(
            summary["blockers"]["years_or_degree"]["control"]["false_positives"],
            ["one"],
        )

    def test_field_domain_verdict_pooling_and_asymmetric_cutoffs(self):
        import compare_decision_field_domain as fd_bench

        self.assertIn(
            "advertisers, agencies, or SMBs",
            fd_bench.FULL_CONTEXT_QUESTION["instructions"],
        )
        gap_answer = {
            "choice": "required_gap",
            "probabilities": {
                "required_gap": 0.40,
                "central_gap": 0.30,
                "required_met": 0.10,
                "central_met": 0.05,
                "preferred": 0.05,
                "absent": 0.05,
                "unclear": 0.05,
            },
        }
        self.assertEqual(
            bench._field_domain_verdict_choice({"field_domain": gap_answer}),
            "flagged",
        )
        self.assertEqual(
            fd_bench._judge(
                gap_answer, fd_bench.VERDICT_GROUPS, 0.40, flag_cutoff=0.65
            )["prediction"],
            "flagged",
        )
        borderline_gap = {
            "choice": "central_gap",
            "probabilities": {
                "required_gap": 0.18,
                "central_gap": 0.40,
                "required_met": 0.05,
                "central_met": 0.07,
                "preferred": 0.15,
                "absent": 0.10,
                "unclear": 0.05,
            },
        }
        self.assertEqual(
            bench._field_domain_verdict_choice({"field_domain": borderline_gap}),
            "unclear",
        )
        self.assertEqual(
            fd_bench._judge(
                borderline_gap, fd_bench.VERDICT_GROUPS, 0.40, flag_cutoff=0.65
            )["prediction"],
            "unclear",
        )
        clear_answer = {
            "choice": "preferred",
            "probabilities": {
                "required_gap": 0.05,
                "central_gap": 0.10,
                "required_met": 0.10,
                "central_met": 0.10,
                "preferred": 0.35,
                "absent": 0.20,
                "unclear": 0.10,
            },
        }
        self.assertEqual(
            bench._field_domain_verdict_choice({"field_domain": clear_answer}),
            "not_flagged",
        )
        self.assertEqual(
            fd_bench._judge(
                clear_answer, fd_bench.VERDICT_GROUPS, 0.40, flag_cutoff=0.65
            )["prediction"],
            "not_flagged",
        )
