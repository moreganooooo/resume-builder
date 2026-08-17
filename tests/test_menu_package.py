import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
    ),
)

import menu


class TestMenuPackage(unittest.TestCase):

    def test_build_documents_choices_includes_package_flow(self):
        choices = menu._build_build_documents_choices()
        values = [c.value for c in choices if hasattr(c, "value")]
        self.assertIn("package_flow", values)

    @patch("picker.browse_and_select_jds")
    @patch("orchestrator.ResumeEngine.build_application_package")
    def test_handle_package_flow_completed(self, mock_build, mock_picker):
        mock_picker.return_value = [{"path": "jds/test_job.json"}]
        mock_build.return_value = {"status": "completed", "output_paths": {}}

        res = menu._handle_package_flow()
        self.assertTrue(res)
        mock_build.assert_called_once_with(
            jd_path="jds/test_job.json", interactive=True
        )

    @patch("picker.browse_and_select_jds")
    def test_handle_package_flow_declined(self, mock_picker):
        mock_picker.return_value = []
        res = menu._handle_package_flow()
        self.assertFalse(res)


if __name__ == "__main__":
    unittest.main()
