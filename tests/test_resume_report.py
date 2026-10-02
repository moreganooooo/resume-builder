"""Reading a generated resume's stored critique back off disk.

The scores these tests cover were, until 2026-09-30, thrown away by the very
builds whose scores mattered most: `_critique` survived only when ZERO
critique recommendations were applied, because every step that replaces
resume_data with a model rewrite rebuilt it from the model's response, and
the model is never sent our underscore-prefixed metadata.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402
import profile_paths  # noqa: E402
import resume_report  # noqa: E402

CRITIQUE = {
    "summary_alignment_score": 92,
    "skills_relevance_score": 88,
    "top_third_score": 79,
    "overall_fit_score": 90,
    "primary_identity": "Content Strategist",
    "secondary_identity": "Lifecycle Marketer",
    "recruiter_takeaway": "A strategist who ships.",
    "strongest_alignment": "content_to_jd",
    "weakest_alignment": "education_specificity",
    "weakest_ats_platform": "Taleo",
    "flags": ["minor_tool_formatting_overlap"],
    "flat_sections": ["Education"],
    "distinctive_moments": ["Founded a content committee."],
    "hard_failures_triggered": [],
}


def _doc(critique=None, applied=None, skipped=None, needs_polish=None, meta=None):
    data = {"SUMMARY_TEXT": "x", "SKILLS": [], "EXPERIENCE": []}
    if critique is not None:
        data["_critique"] = critique
    data["_recommendation_actions"] = {
        "applied": applied or [],
        "skipped": skipped or [],
        "needs_polish": needs_polish or [],
    }
    if meta:
        data["_build_meta"] = meta
    return data


class TestCarryBuildMetadata(unittest.TestCase):
    """The fix that makes the whole feature possible."""

    def test_metadata_survives_a_model_rewrite(self):
        previous = {"SUMMARY_TEXT": "old", "_critique": CRITIQUE}
        candidate = {"SUMMARY_TEXT": "new"}
        result = orchestrator._carry_build_metadata(previous, candidate)
        self.assertEqual(result["_critique"], CRITIQUE)
        self.assertEqual(result["SUMMARY_TEXT"], "new", "content must not revert")

    def test_document_content_is_never_carried(self):
        previous = {"SUMMARY_TEXT": "old", "SKILLS": ["a"]}
        result = orchestrator._carry_build_metadata(previous, {"SUMMARY_TEXT": "new"})
        self.assertNotIn("SKILLS", result)

    def test_an_existing_key_on_the_candidate_wins(self):
        """A step that deliberately sets metadata must not be overwritten by
        the stale value it replaced."""
        previous = {"_critique": {"overall_fit_score": 1}}
        candidate = {"_critique": {"overall_fit_score": 99}}
        result = orchestrator._carry_build_metadata(previous, candidate)
        self.assertEqual(result["_critique"]["overall_fit_score"], 99)

    def test_tolerates_empty_previous(self):
        self.assertEqual(orchestrator._carry_build_metadata({}, {"a": 1}), {"a": 1})
        self.assertEqual(orchestrator._carry_build_metadata(None, {"a": 1}), {"a": 1})


class TestVintage(unittest.TestCase):
    """A fit score the reader cannot date is worse than no fit score."""

    def test_no_edits_after_scoring_is_final(self):
        self.assertTrue(resume_report.report_is_final(_doc(CRITIQUE)))

    def test_an_applied_edit_makes_it_stale(self):
        doc = _doc(CRITIQUE, applied=["Name the AI tools."])
        self.assertFalse(resume_report.report_is_final(doc))
        self.assertEqual(
            resume_report.edits_after_critique(doc), ["Name the AI tools."]
        )

    def test_skipped_and_deferred_are_not_edits(self):
        """They changed nothing, so they cannot have moved a score."""
        doc = _doc(CRITIQUE, skipped=["Go networking."], needs_polish=["Tell me why."])
        self.assertTrue(resume_report.report_is_final(doc))
        self.assertEqual(resume_report.edits_after_critique(doc), [])

    def test_no_critique_is_not_final(self):
        self.assertFalse(resume_report.report_is_final(_doc(None)))


class TestCritiqueFindings(unittest.TestCase):
    def test_collects_critique_findings(self):
        sections = dict(resume_report.critique_findings(_doc(CRITIQUE)))
        self.assertEqual(sections["Flags"], ["minor_tool_formatting_overlap"])
        self.assertEqual(sections["Flat sections"], ["Education"])

    def test_empty_lists_are_omitted(self):
        sections = dict(resume_report.critique_findings(_doc(CRITIQUE)))
        self.assertNotIn("Rubric hard failures", sections)


class TestRecommendationOutcomes(unittest.TestCase):
    """Every recommendation is shown with what became of it -- including the
    ones the apply loop called not-a-document-edit, which it gets wrong often
    enough that hiding them kept real edits from the only person who can
    judge them."""

    def _critique(self, recs):
        return {**CRITIQUE, "recommendations": recs}

    def test_applied_recommendations_are_marked(self):
        doc = _doc(
            self._critique(["Name the AI tools."]), applied=["Name the AI tools."]
        )
        self.assertEqual(
            resume_report.recommendation_outcomes(doc),
            [(resume_report.OUTCOME_APPLIED, "Name the AI tools.")],
        )

    def test_not_an_edit_is_shown_not_hidden(self):
        doc = _doc(self._critique(["Go to a meetup."]), skipped=["Go to a meetup."])
        self.assertEqual(
            resume_report.recommendation_outcomes(doc),
            [(resume_report.OUTCOME_NOT_AN_EDIT, "Go to a meetup.")],
        )

    def test_discarded_is_distinguished_from_not_an_edit(self):
        """One conflicted with a validator rule; the other was judged not to
        be an edit at all. Same list, different marks."""
        doc = _doc(
            self._critique(["Rec A"]),
            skipped=[
                "Rec A (attempted 3x, discarded: introduced a validator violation)"
            ],
        )
        self.assertEqual(
            resume_report.recommendation_outcomes(doc),
            [(resume_report.OUTCOME_DISCARDED, "Rec A")],
        )

    def test_needs_input_is_marked(self):
        doc = _doc(
            self._critique(["Why did it matter?"]), needs_polish=["Why did it matter?"]
        )
        self.assertEqual(
            resume_report.recommendation_outcomes(doc),
            [(resume_report.OUTCOME_NEEDS_INPUT, "Why did it matter?")],
        )

    def test_a_recommendation_nothing_was_tried_on_is_unattempted(self):
        """Exactly what a fresh re-score produces."""
        doc = _doc(self._critique(["Brand new idea."]))
        self.assertEqual(
            resume_report.recommendation_outcomes(doc),
            [(resume_report.OUTCOME_UNATTEMPTED, "Brand new idea.")],
        )

    def test_applied_sorts_before_unattempted(self):
        doc = _doc(
            self._critique(["Untouched", "Landed"]),
            applied=["Landed"],
        )
        self.assertEqual(
            [o for o, _ in resume_report.recommendation_outcomes(doc)],
            [resume_report.OUTCOME_APPLIED, resume_report.OUTCOME_UNATTEMPTED],
        )

    def test_an_action_on_a_dropped_recommendation_still_shows(self):
        """A re-score replaces the recommendation list; what was already done
        must not vanish with the old one."""
        doc = _doc(self._critique(["Fresh idea"]), applied=["An older, replaced idea"])
        rows = resume_report.recommendation_outcomes(doc)
        self.assertIn((resume_report.OUTCOME_APPLIED, "An older, replaced idea"), rows)

    def test_every_outcome_has_a_mark_and_a_label(self):
        for outcome in resume_report.OUTCOME_ORDER:
            self.assertIn(outcome, resume_report.OUTCOME_MARKS)
            self.assertIn(outcome, resume_report.OUTCOME_LABELS)


class TestSampleExclusion(unittest.TestCase):
    """A sample build is a QA smoke test re-run against a fixed fixture --
    its scores describe the pipeline, not an application."""

    def test_build_meta_naming_the_fixture_marks_it_a_sample(self):
        sample = resume_report.sample_jd_path()
        doc = _doc(CRITIQUE, meta={"jd_path": sample})
        self.assertTrue(
            resume_report.is_sample_resume("/out/Whatever_Resume.json", doc)
        )

    def test_build_meta_naming_a_real_jd_does_not(self):
        doc = _doc(CRITIQUE, meta={"jd_path": "/jds/morgan/2026_Acme_Role.json"})
        self.assertFalse(
            resume_report.is_sample_resume("/out/Whatever_Resume.json", doc)
        )

    def test_recorded_jd_beats_the_stem_heuristic(self):
        """A real build that happens to share the fixture's company/role must
        not be hidden -- an explicit answer beats a guess."""
        stem = resume_report._sample_stem()
        if not stem:
            self.skipTest("no sample fixture resolvable for this profile")
        path = f"/out/{stem}_Resume.json"
        doc = _doc(CRITIQUE, meta={"jd_path": "/jds/morgan/2026_Real_Posting.json"})
        self.assertFalse(resume_report.is_sample_resume(path, doc))

    def test_legacy_documents_fall_back_to_the_stem(self):
        stem = resume_report._sample_stem()
        if not stem:
            self.skipTest("no sample fixture resolvable for this profile")
        self.assertTrue(
            resume_report.is_sample_resume(f"/out/{stem}_Resume.json", _doc(CRITIQUE))
        )
        self.assertFalse(
            resume_report.is_sample_resume(
                "/out/Someone_Other_Co_Resume.json", _doc(CRITIQUE)
            )
        )


class TestBuildReport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(
            self._tmp.name, "Me_ContentStrategist_AbnormalAI_Resume.json"
        )

    def _write(self, doc):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(doc, f)

    def test_reports_scores_and_provenance(self):
        self._write(
            _doc(
                CRITIQUE,
                meta={
                    "jd_path": "/jds/morgan/abnormal.json",
                    "built_at": "2026-09-30T10:00:00",
                },
            )
        )
        report = resume_report.build_report(self.path)
        self.assertTrue(report["has_critique"])
        self.assertTrue(report["is_final"])
        self.assertEqual(dict(report["scores"])["Overall fit"], 90)
        self.assertEqual(report["built_at"], "2026-09-30T10:00:00")
        self.assertIn("abnormal", report["jd_path"])

    def test_missing_scores_are_dropped_not_shown_as_none(self):
        self._write(_doc({"overall_fit_score": 90}))
        labels = [label for label, _ in resume_report.build_report(self.path)["scores"]]
        self.assertEqual(labels, ["Overall fit"])

    def test_a_resume_with_no_critique_reports_cleanly(self):
        self._write(_doc(None))
        report = resume_report.build_report(self.path)
        self.assertFalse(report["has_critique"])
        self.assertEqual(report["scores"], [])

    def test_an_unreadable_file_does_not_raise(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        report = resume_report.build_report(self.path)
        self.assertFalse(report["has_critique"])

    def test_title_is_readable(self):
        self.assertEqual(
            resume_report.describe_stem(self.path),
            "Content Strategist / Abnormal AI",
        )


class TestRescore(unittest.TestCase):
    """The one thing here that costs quota -- so it must not spend a call it
    cannot use, and must record that it ran."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = os.path.join(self._tmp.name, "Me_Role_Co_Resume.json")
        self.jd_path = os.path.join(self._tmp.name, "posting.json")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump({"description": "A real posting body."}, f)

    def _write(self, doc):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(doc, f)

    @patch("orchestrator.ResumeEngine")
    def test_refuses_without_a_recorded_jd(self, mock_engine):
        self._write(_doc(CRITIQUE))
        result = resume_report.rescore(self.path)
        self.assertFalse(result["ok"])
        self.assertIn("does not record which JD", result["error"])
        mock_engine.assert_not_called()

    @patch("orchestrator.ResumeEngine")
    def test_refuses_when_the_jd_is_gone(self, mock_engine):
        self._write(_doc(CRITIQUE, meta={"jd_path": "/nope/missing.json"}))
        result = resume_report.rescore(self.path)
        self.assertFalse(result["ok"])
        self.assertIn("gone", result["error"])
        mock_engine.assert_not_called()

    @patch("orchestrator.ResumeEngine")
    def test_scores_and_marks_the_result_final(self, mock_engine):
        self._write(
            _doc(
                CRITIQUE,
                applied=["An edit that landed"],
                meta={"jd_path": self.jd_path},
            )
        )

        def fake_critique(**kwargs):
            kwargs["resume_data"]["_critique"] = {**CRITIQUE, "overall_fit_score": 97}

        engine = mock_engine.return_value
        engine._run_holistic_critique.side_effect = fake_critique
        engine.build_audit_static_prefix.return_value = "prefix"

        result = resume_report.rescore(self.path)
        self.assertTrue(result["ok"], result.get("error"))

        # A re-score happened against the current file, so the scores are
        # final even though the build applied an edit after its own critique.
        self.assertTrue(result["report"]["is_final"])
        self.assertEqual(dict(result["report"]["scores"])["Overall fit"], 97)

        # And it reached disk, not just the returned report.
        with open(self.path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["_critique"]["overall_fit_score"], 97)
        self.assertEqual(
            saved["_critique"]["_scored_at_stage"], resume_report.RESCORED_STAGE
        )
        # The build's own history survives -- it is still true that those
        # edits predate the ORIGINAL scores.
        self.assertEqual(
            saved["_recommendation_actions"]["applied"], ["An edit that landed"]
        )

    @patch("orchestrator.ResumeEngine")
    def test_never_checkpoints_under_the_build_job_key(self, mock_engine):
        """Checkpointing a critique under a finished job's key would make a
        later resumed build reuse a critique of a different draft."""
        self._write(_doc(CRITIQUE, meta={"jd_path": self.jd_path, "job_key": "abc123"}))
        engine = mock_engine.return_value
        engine._run_holistic_critique.side_effect = lambda **kw: kw[
            "resume_data"
        ].__setitem__("_critique", dict(CRITIQUE))
        engine.build_audit_static_prefix.return_value = "prefix"
        resume_report.rescore(self.path)
        self.assertIsNone(engine._run_holistic_critique.call_args.kwargs["job_key"])

    @patch("orchestrator.ResumeEngine")
    def test_an_empty_critique_saves_nothing(self, mock_engine):
        self._write(_doc(CRITIQUE, meta={"jd_path": self.jd_path}))
        engine = mock_engine.return_value
        engine._run_holistic_critique.side_effect = lambda **kw: kw["resume_data"].pop(
            "_critique", None
        )
        engine.build_audit_static_prefix.return_value = "prefix"
        result = resume_report.rescore(self.path)
        self.assertFalse(result["ok"])
        with open(self.path, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["_critique"], CRITIQUE)


class TestResumeJsonPaths(unittest.TestCase):
    def _sandbox(self, tmp):
        """A sandboxed profile that actually exists on disk.

        isolate_for_tests redirects all four roots but creates no profile,
        and active_profile() fails closed on a name with no directory --
        deliberately, since the alternative is silently handing one user
        another's paths.
        """
        os.makedirs(os.path.join(tmp, "profiles", "reporttest"), exist_ok=True)
        previous = os.environ.get("RESUME_PROFILE")
        os.environ["RESUME_PROFILE"] = "reporttest"
        self.addCleanup(
            lambda: (
                os.environ.__setitem__("RESUME_PROFILE", previous)
                if previous is not None
                else os.environ.pop("RESUME_PROFILE", None)
            )
        )

    def test_lists_newest_first_and_skips_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            with profile_paths.isolate_for_tests(tmp):
                self._sandbox(tmp)
                out = resume_report.resume_json_dir()
                os.makedirs(out, exist_ok=True)
                older = os.path.join(out, "A_Old_Co_Resume.json")
                newer = os.path.join(out, "A_New_Co_Resume.json")
                backup = os.path.join(out, "A_New_Co_Resume.json.bak")
                for path in (older, newer, backup):
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump({}, f)
                os.utime(older, (1, 1))
                paths = resume_report.resume_json_paths()
                self.assertEqual(paths, [newer, older])

    def test_directory_is_resolved_per_call(self):
        """A module-level constant here would survive a profile switch and
        show one profile's documents to another."""
        with tempfile.TemporaryDirectory() as tmp:
            with profile_paths.isolate_for_tests(tmp):
                self._sandbox(tmp)
                self.assertTrue(resume_report.resume_json_dir().startswith(tmp))


if __name__ == "__main__":
    unittest.main()
