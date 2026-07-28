import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import audit_keepers  # noqa: E402


class TestResolveSourceFile(unittest.TestCase):
    # Regression coverage for the bug this function exists to prevent: a
    # bare `audit_keepers.py` re-run silently discarding manual corrections
    # (retags, reworded bullets, fixed metrics) that were only ever applied
    # directly to bullet-bank-keepers-audited.csv, by rebuilding from the
    # older bullet-bank-keepers.csv instead.

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.keepers_in = os.path.join(self._tmpdir.name, "bullet-bank-keepers.csv")
        self.keepers_audited = os.path.join(self._tmpdir.name, "bullet-bank-keepers-audited.csv")

    def tearDown(self):
        self._tmpdir.cleanup()

    def _touch(self, path):
        with open(path, "w") as f:
            f.write("")

    def test_defaults_to_audited_file_when_it_exists(self):
        self._touch(self.keepers_in)
        self._touch(self.keepers_audited)
        result = audit_keepers.resolve_source_file(False, self.keepers_in, self.keepers_audited)
        self.assertEqual(result, self.keepers_audited)

    def test_falls_back_to_keepers_in_when_no_audited_file_exists_yet(self):
        self._touch(self.keepers_in)
        result = audit_keepers.resolve_source_file(False, self.keepers_in, self.keepers_audited)
        self.assertEqual(result, self.keepers_in)

    def test_rebuild_flag_forces_keepers_in_even_when_audited_exists(self):
        self._touch(self.keepers_in)
        self._touch(self.keepers_audited)
        result = audit_keepers.resolve_source_file(True, self.keepers_in, self.keepers_audited)
        self.assertEqual(result, self.keepers_in)


class TestNormalizeClusterId(unittest.TestCase):

    def test_int_and_matching_float_normalize_identically(self):
        self.assertEqual(audit_keepers._normalize_cluster_id(37), "37")
        self.assertEqual(audit_keepers._normalize_cluster_id(37.0), "37")
        self.assertEqual(audit_keepers._normalize_cluster_id("37"), "37")
        self.assertEqual(audit_keepers._normalize_cluster_id("37.0"), "37")

    def test_blank_and_nan_normalize_to_empty_string(self):
        self.assertEqual(audit_keepers._normalize_cluster_id(""), "")
        self.assertEqual(audit_keepers._normalize_cluster_id(None), "")
        self.assertEqual(audit_keepers._normalize_cluster_id(float("nan")), "")
        self.assertEqual(audit_keepers._normalize_cluster_id("nan"), "")

    def test_non_numeric_id_falls_back_to_plain_string(self):
        self.assertEqual(audit_keepers._normalize_cluster_id("cluster-a"), "cluster-a")


class TestMergeNewRowsFromKeepersInRealCsvRoundTrip(unittest.TestCase):
    # Regression test for the exact failure this had in production: a
    # DataFrame built in-memory with clean string cluster_ids (as the
    # TestMergeNewRowsFromKeepersIn tests below do) never exercises
    # pandas's own dtype inference, so it can't catch what only shows up
    # after a real pd.read_csv() round-trip. The first time this ran for
    # real, one freshly-triaged row with a blank cluster_id in
    # keepers.csv forced pandas to upcast that whole column to float64
    # ("37" -> 37.0 -> "37.0" on str()), which no longer string-matched
    # the audited file's clean int64 column ("37") -- misclassifying
    # ~810 already-processed rows as "new" and queuing the entire bank
    # for re-scoring instead of the ~25 rows that were actually new.

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmpdir.cleanup()

    def _write_csv(self, filename, rows):
        path = os.path.join(self._tmpdir.name, filename)
        pd.DataFrame(rows).to_csv(path, index=False)
        return path

    def test_blank_cluster_id_on_one_new_row_does_not_orphan_the_rest(self):
        audited_path = self._write_csv("audited.csv", [
            {"Bullet Point": f"Existing bullet {i}", "source_cluster_id": i}
            for i in range(1, 11)
        ])
        keepers_in_path = self._write_csv("keepers_in.csv", [
            *[{"Bullet Point": f"Existing bullet {i}", "source_cluster_id": i} for i in range(1, 11)],
            {"Bullet Point": "Brand new triaged bullet", "source_cluster_id": ""},
        ])

        df_audited = pd.read_csv(audited_path)
        df_keepers_in = pd.read_csv(keepers_in_path)
        # Confirms the setup actually reproduces the dtype mismatch this
        # test exists to catch -- if pandas ever stops upcasting on a
        # blank numeric cell, this assertion (not the real one below)
        # is what would need updating.
        self.assertEqual(df_keepers_in["source_cluster_id"].dtype, float)
        self.assertEqual(df_audited["source_cluster_id"].dtype, int)

        merged, n_new = audit_keepers.merge_new_rows_from_keepers_in(df_audited, df_keepers_in)
        self.assertEqual(n_new, 1)
        self.assertEqual(len(merged), 11)
        self.assertIn("Brand new triaged bullet", merged["Bullet Point"].values)


class TestMergeNewRowsFromKeepersIn(unittest.TestCase):
    # Regression coverage for the gap the audited-file default introduced:
    # triage_needs_review.py appends new KEEP rows straight into
    # bullet-bank-keepers.csv on every real resume-build session, and those
    # must still reach the pipeline even though resolve_source_file() now
    # defaults to loading from the audited file instead.

    def _df(self, bullets, cluster_ids=None, extra_col=None):
        data = {"Bullet Point": bullets, "Role / Company": ["Acme"] * len(bullets)}
        data["source_cluster_id"] = cluster_ids if cluster_ids is not None else [""] * len(bullets)
        if extra_col:
            data[extra_col] = ["x"] * len(bullets)
        return pd.DataFrame(data)

    def test_new_bullet_in_keepers_in_gets_unioned_in(self):
        df_audited = self._df(["Existing bullet"], cluster_ids=["1"])
        df_keepers_in = self._df(["Existing bullet", "Brand new triaged bullet"], cluster_ids=["1", "2"])
        merged, n_new = audit_keepers.merge_new_rows_from_keepers_in(df_audited, df_keepers_in)
        self.assertEqual(n_new, 1)
        self.assertEqual(len(merged), 2)
        self.assertIn("Brand new triaged bullet", merged["Bullet Point"].values)

    def test_no_new_rows_when_keepers_in_has_nothing_new(self):
        df_audited = self._df(["Existing bullet"], cluster_ids=["1"])
        df_keepers_in = self._df(["Existing bullet"], cluster_ids=["1"])
        merged, n_new = audit_keepers.merge_new_rows_from_keepers_in(df_audited, df_keepers_in)
        self.assertEqual(n_new, 0)
        self.assertEqual(len(merged), 1)

    def test_missing_column_on_new_row_filled_not_dropped(self):
        df_audited = self._df(["Existing bullet"], cluster_ids=["1"], extra_col="audit_status")
        df_keepers_in = self._df(["New bullet"], cluster_ids=["2"])  # no audit_status column
        merged, n_new = audit_keepers.merge_new_rows_from_keepers_in(df_audited, df_keepers_in)
        self.assertEqual(n_new, 1)
        new_row = merged[merged["Bullet Point"] == "New bullet"].iloc[0]
        self.assertEqual(new_row["audit_status"], "")

    def test_edited_bullet_text_is_not_reintroduced_as_a_duplicate(self):
        # This is the real regression this test guards against: a bullet
        # manually corrected directly in the audited file (different text,
        # same source_cluster_id) must NOT be treated as "new" just
        # because its wording no longer matches the stale keepers_in row
        # for the same cluster -- text-only matching would re-add the old,
        # uncorrected wording as a duplicate row.
        df_audited = self._df(
            ["Championed Outreach.io's adoption and drove CRM integration."],
            cluster_ids=["108"],
        )
        df_keepers_in = self._df(
            ["Led selection and implementation of Outreach.io, managing CRM integration."],
            cluster_ids=["108"],
        )
        merged, n_new = audit_keepers.merge_new_rows_from_keepers_in(df_audited, df_keepers_in)
        self.assertEqual(n_new, 0)
        self.assertEqual(len(merged), 1)
        self.assertNotIn("Led selection and implementation", merged["Bullet Point"].iloc[0])

    def test_falls_back_to_text_match_when_cluster_id_is_missing(self):
        df_audited = self._df(["Existing bullet"], cluster_ids=[""])
        df_keepers_in = self._df(["Existing bullet", "New bullet"], cluster_ids=["", ""])
        merged, n_new = audit_keepers.merge_new_rows_from_keepers_in(df_audited, df_keepers_in)
        self.assertEqual(n_new, 1)
        self.assertIn("New bullet", merged["Bullet Point"].values)


class TestRemoveRowsMatchingBulletText(unittest.TestCase):

    def test_removes_all_exact_matches_including_duplicates(self):
        df = pd.DataFrame([
            {"Bullet Point": "Same bullet.", "Role / Company": "Acme"},
            {"Bullet Point": "Same bullet.", "Role / Company": "Acme"},
            {"Bullet Point": "Different bullet.", "Role / Company": "Acme"},
        ])
        filtered, n = audit_keepers._remove_rows_matching_bullet_text(df, "Same bullet.")
        self.assertEqual(n, 2)
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]["Bullet Point"], "Different bullet.")

    def test_no_match_removes_nothing(self):
        df = pd.DataFrame([{"Bullet Point": "Untouched.", "Role / Company": "Acme"}])
        filtered, n = audit_keepers._remove_rows_matching_bullet_text(df, "Not present.")
        self.assertEqual(n, 0)
        self.assertEqual(len(filtered), 1)

    def test_missing_bullet_point_column_is_a_safe_no_op(self):
        df = pd.DataFrame()
        filtered, n = audit_keepers._remove_rows_matching_bullet_text(df, "Anything.")
        self.assertEqual(n, 0)
        self.assertEqual(len(filtered), 0)

    def test_blank_bullet_text_is_a_safe_no_op(self):
        df = pd.DataFrame([{"Bullet Point": "", "Role / Company": "Acme"}])
        filtered, n = audit_keepers._remove_rows_matching_bullet_text(df, "")
        self.assertEqual(n, 0)
        self.assertEqual(len(filtered), 1)


class TestStage4AutoRewriteStartsOnFlashLite(unittest.TestCase):

    def setUp(self):
        # stage4_auto_rewrite writes MANUAL results to MANUAL_ATTEMPTS_OUT
        # (see _record_manual_attempt) AND, since the MANUAL branch now
        # saves df_keepers directly (so a removed superseded row survives
        # an interrupted run), also writes to KEEPERS_AUDITED -- isolate
        # every test from the real profile's knowledge_base files.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patchers = [
            patch("audit_keepers.MANUAL_ATTEMPTS_OUT", os.path.join(self._tmpdir.name, "audit-manual-attempts.csv")),
            patch("audit_keepers.KEEPERS_AUDITED", os.path.join(self._tmpdir.name, "bullet-bank-keepers-audited.csv")),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        self._tmpdir.cleanup()

    @patch("audit_keepers.append_keeper")
    @patch("audit_keepers.process_bullet")
    def test_passes_fallback_model_as_start_model(self, mock_process_bullet, mock_append_keeper):
        # Stage 4's whole queue is bullets that already failed a first
        # Gemma-led pass -- confirm it skips straight to flash-lite rather
        # than spending another Gemma attempt on bullets already known to
        # need the stronger model.
        mock_process_bullet.return_value = {"rewrite_status": "MANUAL"}
        df_queue = pd.DataFrame([{"Bullet Point": "A weak bullet.", "Role / Company": "Acme"}])

        audit_keepers.stage4_auto_rewrite(
            df_queue=df_queue,
            kb=object(),
            rewrite_system="sys",
            rewrite_system_gemma="sys-gemma",
            score_system="score-sys",
            df_keepers=pd.DataFrame(),
            dry_run=False,
        )

        mock_process_bullet.assert_called_once()
        call_kwargs = mock_process_bullet.call_args.kwargs
        self.assertEqual(call_kwargs["start_model"], audit_keepers.REWRITE_FALLBACK_MODEL)
        self.assertEqual(audit_keepers.REWRITE_FALLBACK_MODEL, "gemini-3.1-flash-lite")

    @patch("audit_keepers.append_keeper")
    @patch("audit_keepers.process_bullet")
    def test_manual_result_is_recorded_with_its_cluster_id(self, mock_process_bullet, mock_append_keeper):
        # A bullet that stays MANUAL must be recorded in
        # audit-manual-attempts.csv so Stage 3 can exclude its cluster_id
        # from future queues -- otherwise every run re-attempts the exact
        # same failures forever (the bug this fix addresses).
        mock_process_bullet.return_value = {"rewrite_status": "MANUAL", "manager_test": "FAIL", "rewrite_attempts": 3}
        df_queue = pd.DataFrame([{
            "Bullet Point": "A weak bullet.", "Role / Company": "Acme",
            "cluster_id": 42, "composite_score": 220,
        }])

        audit_keepers.stage4_auto_rewrite(
            df_queue=df_queue,
            kb=object(),
            rewrite_system="sys",
            rewrite_system_gemma="sys-gemma",
            score_system="score-sys",
            df_keepers=pd.DataFrame(),
            dry_run=False,
        )

        recorded = audit_keepers._known_manual_attempt_cluster_ids()
        self.assertEqual(recorded, {42})

    @patch("audit_keepers.append_keeper")
    @patch("audit_keepers.process_bullet")
    def test_manual_result_from_keeper_audit_source_is_recorded_with_its_cluster_id(
        self, mock_process_bullet, mock_append_keeper,
    ):
        # Regression: Source A rows (bullets already in keepers-audited.csv,
        # marked MANUAL/NEEDS_REWRITE) carry their cluster ID under
        # "source_cluster_id", not "cluster_id" -- the column Source B
        # (cluster-map) rows use. The old code only ever checked
        # "cluster_id", so every Source A MANUAL bullet was silently
        # recorded with an empty cluster_id and could never be excluded by
        # Stage 3's manual-attempt check -- confirmed live: the same 6
        # keeper-audit-sourced bullets kept re-queuing every single run.
        mock_process_bullet.return_value = {"rewrite_status": "MANUAL", "manager_test": "FAIL", "rewrite_attempts": 3}
        df_queue = pd.DataFrame([{
            "Bullet Point": "A weak bullet.", "Role / Company": "Acme",
            "source_cluster_id": 99, "composite_score": 220,
        }])

        audit_keepers.stage4_auto_rewrite(
            df_queue=df_queue,
            kb=object(),
            rewrite_system="sys",
            rewrite_system_gemma="sys-gemma",
            score_system="score-sys",
            df_keepers=pd.DataFrame(),
            dry_run=False,
        )

        recorded = audit_keepers._known_manual_attempt_cluster_ids()
        self.assertEqual(recorded, {99})

    @patch("audit_keepers.append_keeper")
    @patch("audit_keepers.process_bullet")
    def test_keep_result_is_not_recorded_as_a_manual_attempt(self, mock_process_bullet, mock_append_keeper):
        mock_process_bullet.return_value = {
            "rewrite_status": "KEEP", "final_bullet": "A great bullet.", "rewrite_attempts": 1,
        }
        mock_append_keeper.side_effect = lambda df, row, path: df
        df_queue = pd.DataFrame([{"Bullet Point": "A weak bullet.", "Role / Company": "Acme", "cluster_id": 7}])

        audit_keepers.stage4_auto_rewrite(
            df_queue=df_queue,
            kb=object(),
            rewrite_system="sys",
            rewrite_system_gemma="sys-gemma",
            score_system="score-sys",
            df_keepers=pd.DataFrame(),
            dry_run=False,
        )

        self.assertEqual(audit_keepers._known_manual_attempt_cluster_ids(), set())

    @patch("audit_keepers.process_bullet")
    def test_successful_rewrite_removes_the_superseded_original_and_its_duplicates(self, mock_process_bullet):
        # Regression test for the real bug this was written to fix: Stage 4
        # used to only append_keeper() the new rewritten row, never
        # touching the original NEEDS_REWRITE row it replaced -- so that
        # original (and any exact-duplicate copies of it, e.g. from the
        # same achievement being triaged twice) stayed in df_keepers
        # forever, got re-scored and re-queued on every future run even
        # though a successful rewrite already existed for it.
        mock_process_bullet.return_value = {
            "rewrite_status": "KEEP", "final_bullet": "A great, rewritten bullet.", "rewrite_attempts": 1,
        }
        original_text = "A weak bullet that needs work."
        df_keepers = pd.DataFrame([
            {"Bullet Point": original_text, "Role / Company": "Acme", "audit_status": "NEEDS_REWRITE"},
            {"Bullet Point": original_text, "Role / Company": "Acme", "audit_status": "NEEDS_REWRITE"},  # duplicate
            {"Bullet Point": "An unrelated, already-CLEAN bullet.", "Role / Company": "Acme", "audit_status": "CLEAN"},
        ])
        df_queue = pd.DataFrame([{"Bullet Point": original_text, "Role / Company": "Acme", "cluster_id": 9}])

        result = audit_keepers.stage4_auto_rewrite(
            df_queue=df_queue,
            kb=object(),
            rewrite_system="sys",
            rewrite_system_gemma="sys-gemma",
            score_system="score-sys",
            df_keepers=df_keepers,
            dry_run=False,
        )

        # Both copies of the original are gone -- not just the one that
        # was actually in the queue.
        self.assertEqual((result["Bullet Point"] == original_text).sum(), 0)
        # The unrelated CLEAN row survived untouched.
        self.assertIn("An unrelated, already-CLEAN bullet.", result["Bullet Point"].values)
        # The new rewritten row is present, and only once.
        self.assertEqual((result["Bullet Point"] == "A great, rewritten bullet.").sum(), 1)
        self.assertEqual(len(result), 2)  # unrelated CLEAN + the one new rewrite


class TestStage3ExcludesPreviouslyManualClusters(unittest.TestCase):

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        cluster_map_path = os.path.join(self._tmpdir.name, "cluster-map-updated.csv")
        manual_attempts_path = os.path.join(self._tmpdir.name, "audit-manual-attempts.csv")
        rewrite_queue_path = os.path.join(self._tmpdir.name, "audit-rewrite-queue.csv")

        pd.DataFrame([
            {"cluster_id": 1, "Bullet Point": "Bullet one.", "rewrite_status": "MANUAL", "is_representative": True},
            {"cluster_id": 2, "Bullet Point": "Bullet two.", "rewrite_status": "MANUAL", "is_representative": True},
        ]).to_csv(cluster_map_path, index=False)

        # cluster_id 1 already failed a prior Stage 4 attempt.
        pd.DataFrame([{"cluster_id": 1, "Bullet Point": "Bullet one.", "last_attempted": "2026-07-23 00:00:00"}]) \
            .to_csv(manual_attempts_path, index=False)

        self._patchers = [
            patch("audit_keepers.CLUSTER_MAP_UPDATED", cluster_map_path),
            patch("audit_keepers.CLUSTER_MAP_IN", cluster_map_path),
            patch("audit_keepers.MANUAL_ATTEMPTS_OUT", manual_attempts_path),
            patch("audit_keepers.REWRITE_QUEUE_OUT", rewrite_queue_path),
            patch("audit_keepers._all_known_keeper_cluster_ids", return_value=set()),
            patch("audit_keepers._all_known_keeper_bullets", return_value=set()),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        self._tmpdir.cleanup()

    def _df_keepers(self):
        return pd.DataFrame(columns=["Bullet Point", "audit_status"])

    def test_previously_manual_cluster_excluded_by_default(self):
        df_queue = audit_keepers.stage3_build_rewrite_queue(self._df_keepers())
        self.assertNotIn(1, df_queue["cluster_id"].tolist())
        self.assertIn(2, df_queue["cluster_id"].tolist())

    def test_retry_manual_flag_includes_it_again(self):
        df_queue = audit_keepers.stage3_build_rewrite_queue(self._df_keepers(), retry_manual=True)
        self.assertIn(1, df_queue["cluster_id"].tolist())
        self.assertIn(2, df_queue["cluster_id"].tolist())


class TestStage3ExcludesPreviouslyManualClustersFromSourceA(unittest.TestCase):
    # Regression coverage for a real production bug: Source A (bullets
    # marked MANUAL/NEEDS_REWRITE in bullet-bank-keepers-audited.csv) never
    # checked audit-manual-attempts.csv the way Source B (cluster-map
    # MANUALs) already did. Combined with stage4_auto_rewrite()'s MANUAL
    # branch deleting the keeper row entirely (see
    # _remove_rows_matching_bullet_text()), a bullet that stayed MANUAL
    # would get silently resurrected from keepers.csv by
    # merge_new_rows_from_keepers_in() on the very next run and land right
    # back in the queue -- forever, no forward progress. Confirmed live:
    # the same 6 bullets kept cycling through --auto-rewrite run after run.

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        manual_attempts_path = os.path.join(self._tmpdir.name, "audit-manual-attempts.csv")
        rewrite_queue_path = os.path.join(self._tmpdir.name, "audit-rewrite-queue.csv")

        # cluster_id 1 already failed a prior Stage 4 attempt.
        pd.DataFrame([{"cluster_id": 1, "Bullet Point": "Bullet one.", "last_attempted": "2026-07-23 00:00:00"}]) \
            .to_csv(manual_attempts_path, index=False)

        # No real cluster map at these paths -- Source B safely no-ops
        # ("Cluster map not found") so this test only exercises Source A.
        missing_cluster_map = os.path.join(self._tmpdir.name, "no-such-cluster-map.csv")

        self._patchers = [
            patch("audit_keepers.CLUSTER_MAP_UPDATED", missing_cluster_map),
            patch("audit_keepers.CLUSTER_MAP_IN", missing_cluster_map),
            patch("audit_keepers.MANUAL_ATTEMPTS_OUT", manual_attempts_path),
            patch("audit_keepers.REWRITE_QUEUE_OUT", rewrite_queue_path),
            patch("audit_keepers._all_known_keeper_cluster_ids", return_value=set()),
            patch("audit_keepers._all_known_keeper_bullets", return_value=set()),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        self._tmpdir.cleanup()

    def _df_keepers(self):
        return pd.DataFrame([
            {"Bullet Point": "Bullet one.", "audit_status": "MANUAL", "source_cluster_id": 1},
            {"Bullet Point": "Bullet two.", "audit_status": "MANUAL", "source_cluster_id": 2},
        ])

    def test_previously_manual_cluster_excluded_from_keeper_audit_source(self):
        df_queue = audit_keepers.stage3_build_rewrite_queue(self._df_keepers())
        bullets = df_queue["Bullet Point"].tolist()
        self.assertNotIn("Bullet one.", bullets)
        self.assertIn("Bullet two.", bullets)

    def test_retry_manual_flag_includes_it_again(self):
        df_queue = audit_keepers.stage3_build_rewrite_queue(self._df_keepers(), retry_manual=True)
        bullets = df_queue["Bullet Point"].tolist()
        self.assertIn("Bullet one.", bullets)
        self.assertIn("Bullet two.", bullets)

    def test_a_bullet_never_attempted_before_is_still_queued(self):
        # No prior manual-attempts entry exists for cluster 2 -- must not
        # be excluded just because SOME cluster is in the exclusion set.
        df_queue = audit_keepers.stage3_build_rewrite_queue(self._df_keepers())
        self.assertIn("Bullet two.", df_queue["Bullet Point"].tolist())


if __name__ == "__main__":
    unittest.main()
