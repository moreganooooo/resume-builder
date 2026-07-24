import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import audit_keepers  # noqa: E402


class TestStage4AutoRewriteStartsOnFlashLite(unittest.TestCase):

    def setUp(self):
        # stage4_auto_rewrite writes MANUAL results to MANUAL_ATTEMPTS_OUT
        # (see _record_manual_attempt) -- isolate every test from the real
        # profile's knowledge_base file.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._patcher = patch(
            "audit_keepers.MANUAL_ATTEMPTS_OUT",
            os.path.join(self._tmpdir.name, "audit-manual-attempts.csv"),
        )
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
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


if __name__ == "__main__":
    unittest.main()
