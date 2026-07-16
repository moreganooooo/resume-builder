import csv
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

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


class TestStageStatusChecksCheckpoint(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.checkpoint_path = os.path.join(self.tmp_dir, "checkpoint.npz")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_checkpoint(self, next_index, total):
        import numpy as np
        np.savez(
            self.checkpoint_path,
            vectors=np.zeros((next_index, 4), dtype=np.float32),
            next_index=np.array(next_index),
            total=np.array(total),
        )

    def test_missing_output_with_checkpoint_reports_progress(self):
        self._write_checkpoint(next_index=1035, total=1431)
        stage = {
            "output": os.path.join(self.tmp_dir, "missing.csv"),
            "inputs": [], "status_mode": "mtime",
            "checkpoint": self.checkpoint_path,
        }
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")
        self.assertEqual(detail, "checkpoint at bullet 1035/1431 -- resumable")

    def test_missing_output_without_checkpoint_key_is_unaffected(self):
        stage = {
            "output": os.path.join(self.tmp_dir, "missing.csv"),
            "inputs": [], "status_mode": "mtime",
        }
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")
        self.assertEqual(detail, "")

    def test_missing_output_with_checkpoint_key_but_no_file_is_unaffected(self):
        stage = {
            "output": os.path.join(self.tmp_dir, "missing.csv"),
            "inputs": [], "status_mode": "mtime",
            "checkpoint": os.path.join(self.tmp_dir, "no_such_checkpoint.npz"),
        }
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")
        self.assertEqual(detail, "")


class TestStageStatusProgress(unittest.TestCase):

    def test_in_progress_when_done_less_than_total(self):
        stage = {"status_mode": "progress", "progress_fn": lambda: (3, 10)}
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "In progress")
        self.assertEqual(detail, "3/10 processed (7 pending)")

    def test_falls_through_to_mtime_check_when_done_equals_total(self):
        stage = {
            "status_mode": "progress", "progress_fn": lambda: (10, 10),
            "output": "/does/not/exist.csv", "inputs": [],
        }
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")

    def test_none_progress_falls_through_unaffected(self):
        stage = {
            "status_mode": "progress", "progress_fn": lambda: None,
            "output": "/does/not/exist.csv", "inputs": [],
        }
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")

    def test_zero_total_falls_through_unaffected(self):
        stage = {
            "status_mode": "progress", "progress_fn": lambda: (0, 0),
            "output": "/does/not/exist.csv", "inputs": [],
        }
        status, detail = bullet_bank_menu._stage_status(stage)
        self.assertEqual(status, "Never run")


class TestAuditProgress(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.raw_path = os.path.join(self.tmp_dir, "raw.csv")
        self.audited_path = os.path.join(self.tmp_dir, "audited.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_csv(self, path, rows, fieldnames):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_missing_raw_csv_returns_none(self):
        with patch.object(bullet_bank_menu, "RAW_CSV", os.path.join(self.tmp_dir, "missing.csv")):
            self.assertIsNone(bullet_bank_menu._audit_progress())

    def test_no_output_yet_is_zero_done(self):
        self._write_csv(self.raw_path, [{"Bullet Point": "a"}, {"Bullet Point": "b"}], ["Bullet Point"])
        with patch.object(bullet_bank_menu, "RAW_CSV", self.raw_path), \
             patch.object(bullet_bank_menu, "AUDITED_CSV", os.path.join(self.tmp_dir, "missing.csv")):
            self.assertEqual(bullet_bank_menu._audit_progress(), (0, 2))

    def test_partial_output_counts_scored_rows(self):
        # audit_bullet_bank.py's output only ever contains rows actually
        # scored so far, so row count itself is the done signal.
        self._write_csv(
            self.raw_path,
            [{"Bullet Point": "a"}, {"Bullet Point": "b"}, {"Bullet Point": "c"}],
            ["Bullet Point"],
        )
        self._write_csv(self.audited_path, [{"Bullet Point": "a"}], ["Bullet Point"])
        with patch.object(bullet_bank_menu, "RAW_CSV", self.raw_path), \
             patch.object(bullet_bank_menu, "AUDITED_CSV", self.audited_path):
            self.assertEqual(bullet_bank_menu._audit_progress(), (1, 3))


class TestRewriteProgress(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.cluster_map_path = os.path.join(self.tmp_dir, "cluster_map.csv")
        self.cluster_map_out_path = os.path.join(self.tmp_dir, "cluster_map_out.csv")
        self.keepers_path = os.path.join(self.tmp_dir, "keepers.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_csv(self, path, rows, fieldnames):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_missing_cluster_map_returns_none(self):
        with patch.object(bullet_bank_menu, "CLUSTER_MAP_CSV", os.path.join(self.tmp_dir, "missing.csv")):
            self.assertIsNone(bullet_bank_menu._rewrite_progress())

    def test_partial_completion_counts_done_bullets(self):
        self._write_csv(
            self.cluster_map_path,
            [
                {"Bullet Point": "a", "is_representative": "True", "next_action": "REWRITE"},
                {"Bullet Point": "b", "is_representative": "True", "next_action": "REWRITE"},
                {"Bullet Point": "c", "is_representative": "True", "next_action": "REVIEW"},
                {"Bullet Point": "d", "is_representative": "True", "next_action": "KEEP"},
                {"Bullet Point": "e", "is_representative": "False", "next_action": "REWRITE"},
            ],
            ["Bullet Point", "is_representative", "next_action"],
        )
        # "a" done via cluster-map-out's rewrite_status; "c" done via
        # already being in keepers.csv; "b" still pending. "d" isn't a
        # target (next_action=KEEP) and "e" isn't representative, so
        # total must be 3, not 5.
        self._write_csv(
            self.cluster_map_out_path,
            [{"Bullet Point": "a", "rewrite_status": "KEEP", "final_bullet": "Rewritten a"}],
            ["Bullet Point", "rewrite_status", "final_bullet"],
        )
        self._write_csv(self.keepers_path, [{"Bullet Point": "c"}], ["Bullet Point"])
        with patch.object(bullet_bank_menu, "CLUSTER_MAP_CSV", self.cluster_map_path), \
             patch.object(bullet_bank_menu, "CLUSTER_MAP_OUT_CSV", self.cluster_map_out_path), \
             patch.object(bullet_bank_menu, "KEEPERS_CSV", self.keepers_path):
            self.assertEqual(bullet_bank_menu._rewrite_progress(), (2, 3))

    def test_no_target_rows_returns_zero_zero(self):
        self._write_csv(
            self.cluster_map_path,
            [{"Bullet Point": "a", "is_representative": "True", "next_action": "KEEP"}],
            ["Bullet Point", "is_representative", "next_action"],
        )
        with patch.object(bullet_bank_menu, "CLUSTER_MAP_CSV", self.cluster_map_path), \
             patch.object(bullet_bank_menu, "CLUSTER_MAP_OUT_CSV", os.path.join(self.tmp_dir, "missing.csv")), \
             patch.object(bullet_bank_menu, "KEEPERS_CSV", os.path.join(self.tmp_dir, "missing2.csv")):
            self.assertEqual(bullet_bank_menu._rewrite_progress(), (0, 0))


class TestAuditKeepersProgress(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.keepers_audited_path = os.path.join(self.tmp_dir, "keepers_audited.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_csv(self, path, rows, fieldnames):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_missing_file_returns_none(self):
        with patch.object(bullet_bank_menu, "KEEPERS_AUDITED_CSV", os.path.join(self.tmp_dir, "missing.csv")):
            self.assertIsNone(bullet_bank_menu._audit_keepers_progress())

    def test_blank_audit_status_counts_as_pending(self):
        self._write_csv(
            self.keepers_audited_path,
            [{"Bullet Point": "a", "audit_status": "CLEAN"}, {"Bullet Point": "b", "audit_status": ""}],
            ["Bullet Point", "audit_status"],
        )
        with patch.object(bullet_bank_menu, "KEEPERS_AUDITED_CSV", self.keepers_audited_path):
            self.assertEqual(bullet_bank_menu._audit_keepers_progress(), (1, 2))

    def test_empty_csv_returns_zero_zero(self):
        self._write_csv(self.keepers_audited_path, [], ["Bullet Point", "audit_status"])
        with patch.object(bullet_bank_menu, "KEEPERS_AUDITED_CSV", self.keepers_audited_path):
            self.assertEqual(bullet_bank_menu._audit_keepers_progress(), (0, 0))


class TestEmbedProgress(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.checkpoint_path = os.path.join(self.tmp_dir, "embed.checkpoint.npz")
        self.keepers_audited_path = os.path.join(self.tmp_dir, "keepers_audited.csv")

    def tearDown(self):
        for name in os.listdir(self.tmp_dir):
            os.remove(os.path.join(self.tmp_dir, name))
        os.rmdir(self.tmp_dir)

    def _write_checkpoint(self, next_index):
        import numpy as np
        np.savez(self.checkpoint_path, next_index=np.array(next_index))

    def _write_csv(self, path, rows, fieldnames):
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def test_no_checkpoint_returns_none(self):
        with patch.object(bullet_bank_menu, "EMBED_CHECKPOINT_PATH", os.path.join(self.tmp_dir, "missing.npz")):
            self.assertIsNone(bullet_bank_menu._embed_progress())

    def test_checkpoint_with_keepers_audited_reports_progress(self):
        self._write_checkpoint(next_index=40)
        self._write_csv(
            self.keepers_audited_path, [{"Bullet Point": str(i)} for i in range(100)], ["Bullet Point"],
        )
        with patch.object(bullet_bank_menu, "EMBED_CHECKPOINT_PATH", self.checkpoint_path), \
             patch.object(bullet_bank_menu, "KEEPERS_AUDITED_CSV", self.keepers_audited_path):
            self.assertEqual(bullet_bank_menu._embed_progress(), (40, 100))

    def test_checkpoint_without_keepers_audited_uses_done_as_total(self):
        self._write_checkpoint(next_index=40)
        with patch.object(bullet_bank_menu, "EMBED_CHECKPOINT_PATH", self.checkpoint_path), \
             patch.object(bullet_bank_menu, "KEEPERS_AUDITED_CSV", os.path.join(self.tmp_dir, "missing.csv")):
            self.assertEqual(bullet_bank_menu._embed_progress(), (40, 40))


class TestClusterStageHasCheckpointKey(unittest.TestCase):

    def test_cluster_stage_has_checkpoint_key(self):
        cluster_stage = next(s for s in bullet_bank_menu.STAGES if s["key"] == "cluster")
        self.assertIn("checkpoint", cluster_stage)
        self.assertTrue(cluster_stage["checkpoint"].endswith("_cluster.checkpoint.npz"))


class TestStagesAndMaintenanceDefinitions(unittest.TestCase):

    def test_six_stages_in_pipeline_order(self):
        self.assertEqual([s["key"] for s in bullet_bank_menu.STAGES],
                          ["audit", "cluster", "rewrite", "audit_keepers", "score_gems", "embed"])
        self.assertEqual([s["number"] for s in bullet_bank_menu.STAGES], [1, 2, 3, 4, 5, 6])

    def test_all_stages_cost_api(self):
        self.assertTrue(all(s["api_cost"] for s in bullet_bank_menu.STAGES))

    def test_two_maintenance_scripts(self):
        self.assertEqual([m["key"] for m in bullet_bank_menu.MAINTENANCE], ["triage", "retire"])

    def test_resumable_stages_use_progress_mode_not_mtime(self):
        # audit, rewrite, audit_keepers, and embed all flush partial
        # results to their output file as they run -- an mtime-only check
        # reports "Up to date" the instant ANY output exists, even with
        # most rows still pending. cluster keeps status_mode="mtime"
        # because its final CSV is written once, atomically, only after
        # all in-memory work is done; score_gems keeps "columns" since it
        # updates its file in place.
        by_key = {s["key"]: s for s in bullet_bank_menu.STAGES}
        for key in ("audit", "rewrite", "audit_keepers", "embed"):
            self.assertEqual(by_key[key]["status_mode"], "progress", key)
            self.assertTrue(callable(by_key[key]["progress_fn"]), key)
        self.assertEqual(by_key["cluster"]["status_mode"], "mtime")
        self.assertEqual(by_key["score_gems"]["status_mode"], "columns")


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
