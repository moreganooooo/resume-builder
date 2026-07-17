import os
import sys
import unittest
from unittest.mock import patch

import pandas as pd

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import audit_keepers  # noqa: E402


class TestStage4AutoRewriteStartsOnFlashLite(unittest.TestCase):

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


if __name__ == "__main__":
    unittest.main()
