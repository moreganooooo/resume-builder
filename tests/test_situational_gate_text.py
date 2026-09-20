"""The situational-role gate must not read the CV a recruiter brief embeds.

A CV names every situational job its owner has held, so gating on it
clears every situational role on every recruiter build.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_recruiter_resume  # noqa: E402
import orchestrator  # noqa: E402
import situational_roles  # noqa: E402

ROLES = {
    "situational_min_bullets": 1,
    "roles": {
        "Corner Bakery": {"bank_tag": "Bakery", "trigger_keywords": ["pastry"]},
    },
}
PROFILE = {"target_roles": {"primary": ["Analyst"], "secondary": []}}
CV = "## Experience\n\n### Pastry Chef\n**Corner Bakery**\n- Baked pastry daily."


class TestSituationalGateText(unittest.TestCase):
    def test_recruiter_brief_cv_does_not_clear_the_gate(self):
        brief = build_recruiter_resume.build_target_brief(PROFILE, CV)
        # The raw brief DOES trip the gate -- which is the bug being guarded.
        self.assertEqual(
            situational_roles.detect_situational_candidates(brief, ROLES),
            ["Corner Bakery"],
        )
        gated = orchestrator._situational_gate_text(brief)
        self.assertEqual(
            situational_roles.detect_situational_candidates(gated, ROLES), []
        )

    def test_brief_writer_and_gate_share_one_marker(self):
        brief = build_recruiter_resume.build_target_brief(PROFILE, CV)
        self.assertIn(orchestrator.RECRUITER_CV_MARKER, brief)

    def test_a_real_posting_is_gated_whole(self):
        jd = "Seeking a pastry lead for our morning shift."
        self.assertEqual(orchestrator._situational_gate_text(jd), jd)

    def test_the_brief_role_list_still_reaches_the_gate(self):
        profile = {"target_roles": {"primary": ["Pastry Lead"], "secondary": []}}
        brief = build_recruiter_resume.build_target_brief(profile, CV)
        gated = orchestrator._situational_gate_text(brief)
        self.assertEqual(
            situational_roles.detect_situational_candidates(gated, ROLES),
            ["Corner Bakery"],
        )


if __name__ == "__main__":
    unittest.main()
