"""Matching a status email to the RIGHT saved role.

The failure that matters is a confident wrong match: silently marking a
live application "Rejected" because a different role at the same company
was declined. The Aquent thread in the real mailbox is the worked
example -- five roles, two matched pairs, four unmatched -- and most of
these cases come straight from it.
"""

import os
import sys
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import email_matcher as em  # noqa: E402


class TestRoleExtraction(unittest.TestCase):

    def test_role_from_rejection_subject(self):
        self.assertEqual(
            em.extract_role(
                "Update on your application for Digital Marketing Coordinator",
                "",
                "rejection",
            ),
            "Digital Marketing Coordinator",
        )

    def test_role_from_interest_subject(self):
        self.assertEqual(
            em.extract_role(
                "Thank you for your interest in Copywriter", "", "rejection"
            ),
            "Copywriter",
        )

    def test_company_suffix_is_not_part_of_the_role(self):
        self.assertEqual(
            em.extract_role(
                "Your Application for Content Writer at Aquent | Skill", "", "rejection"
            ),
            "Content Writer",
        )

    def test_role_from_body_for_a_confirmation(self):
        """Confirmations greet the company in the subject and name the
        role in the body."""
        self.assertEqual(
            em.extract_role(
                "Thank you for your application to Aquent | Skill",
                "Thank you for your interest in the Copywriter position at Aquent!",
                "acknowledgment",
            ),
            "Copywriter",
        )

    def test_no_role_returns_none(self):
        self.assertIsNone(
            em.extract_role("Hello there", "Just checking in", "rejection")
        )


class TestRoleNormalization(unittest.TestCase):

    def test_requisition_id_is_stripped(self):
        self.assertEqual(
            em.normalize_role("Content Strategist [AQ-12521]"), "content strategist"
        )

    def test_meaningful_parenthetical_is_kept(self):
        """ "(Commercial B2B)" contains a digit but is part of the role's
        real name -- stripping it merged two different Aquent postings."""
        self.assertIn("b2b", em.normalize_role("Content Strategist (Commercial B2B)"))

    def test_seniority_is_ignored(self):
        self.assertEqual(
            em.normalize_role("Sr. Content Strategist"),
            em.normalize_role("Content Strategist"),
        )


class TestRoleSimilarity(unittest.TestCase):

    def test_identical_roles(self):
        self.assertEqual(em.role_similarity("Copywriter", "Copywriter"), 1.0)

    def test_requisition_id_does_not_reduce_similarity(self):
        self.assertEqual(
            em.role_similarity("Content Strategist", "Content Strategist [AQ-12521]"),
            1.0,
        )

    def test_word_order_is_tolerated(self):
        self.assertGreater(
            em.role_similarity(
                "Marketing Content Manager", "Content Marketing Manager"
            ),
            0.7,
        )

    def test_different_roles_score_low(self):
        self.assertLess(em.role_similarity("Graphic Designer", "Copywriter"), 0.4)


class TestMatching(unittest.TestCase):

    JOBS = [
        {
            "path": "aq.json",
            "title": "Content Strategist [AQ-12521]",
            "company": "Aquent",
            "application": None,
        },
        {
            "path": "cw.json",
            "title": "Copywriter",
            "company": "Aquent",
            "application": None,
        },
    ]

    def _plan(self, subject, intent="rejection", body="", company="Aquent"):
        email = {
            "company": company,
            "subject": subject,
            "body": body,
            "intent": intent,
            "date": "Mon, 16 Jun 2025 12:14:00 -0400",
        }
        return em.plan_updates([email], self.JOBS)

    def test_matching_role_is_proposed(self):
        proposals = self._plan("Update on your application for Copywriter")

        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["job_title"], "Copywriter")
        self.assertEqual(proposals[0]["new_status"], "Rejected")

    def test_a_role_with_no_saved_counterpart_is_not_forced_onto_another(self):
        """The Aquent "Graphic Designer" rejection has no matching saved
        role. Attaching it to Copywriter would be the damaging failure."""
        proposals = self._plan("Update on your application for Graphic Designer")

        for proposal in proposals:
            self.assertEqual(proposal["action"], "skip", f"wrongly proposed {proposal}")

    def test_unknown_company_yields_nothing(self):
        self.assertEqual(
            self._plan("Update on your application for X", company="Nope"), []
        )

    def test_company_key_collapses_spacing(self):
        """A saved "Khan Academy" and a sender-derived "khanacademy" are
        the same company."""
        self.assertEqual(
            em._company_key("Khan Academy"), em._company_key("khanacademy")
        )

    def test_ambiguous_ties_are_demoted_below_auto(self):
        """Two saved roles scoring alike means nothing distinguishes them,
        so a confident write would be a coin flip."""
        jobs = [
            {"path": "a.json", "title": "Content Strategist", "company": "Aquent"},
            {"path": "b.json", "title": "Content Strategist", "company": "Aquent"},
        ]
        email = {
            "company": "Aquent",
            "subject": "Update on your application for Content Strategist",
            "body": "",
            "intent": "rejection",
            "date": "",
        }

        proposals = em.plan_updates([email], jobs)

        self.assertTrue(all(p["action"] != "auto" for p in proposals))


class TestStatusResolution(unittest.TestCase):

    def test_intent_maps_to_status(self):
        self.assertEqual(em.resolve_status("rejection", None), "Rejected")
        self.assertEqual(em.resolve_status("interview", None), "Interview")
        self.assertEqual(em.resolve_status("offer", None), "Offer")

    def test_status_never_moves_backwards(self):
        """A delayed "we received your application" must not undo a
        recorded interview."""
        self.assertIsNone(em.resolve_status("acknowledgment", "Interview"))

    def test_terminal_status_is_not_reopened(self):
        self.assertIsNone(em.resolve_status("interview", "Rejected"))
        self.assertIsNone(em.resolve_status("acknowledgment", "Withdrawn"))

    def test_forward_progress_is_allowed(self):
        self.assertEqual(em.resolve_status("interview", "Applied"), "Interview")

    def test_unmapped_intent_changes_nothing(self):
        self.assertIsNone(em.resolve_status("recruiter_outreach", None))
        self.assertIsNone(em.resolve_status("unknown", "Applied"))

    def test_every_mapped_status_is_a_real_application_status(self):
        import jd_manager

        for status in em.STATUS_MAP.values():
            self.assertIn(status, jd_manager.APPLICATION_STATUSES)


class TestApplyUpdates(unittest.TestCase):

    def test_only_auto_proposals_are_written_by_default(self):
        proposals = [
            {"job_id": "a", "action": "confirm", "new_status": "Rejected"},
            {"job_id": "b", "action": "skip", "new_status": "Rejected"},
        ]

        with patch("jd_source.resolved_jd") as resolved:
            applied = em.apply_updates(proposals)

        self.assertEqual(applied, 0)
        resolved.assert_not_called()

    def test_confirmed_proposals_are_written_when_asked(self):
        proposals = [{"job_id": "a", "action": "confirm", "new_status": "Rejected"}]

        import contextlib

        @contextlib.contextmanager
        def fake_resolved(job_id, profile=None):
            yield ("/tmp/fake.json", True)

        with (
            patch("jd_source.resolved_jd", fake_resolved),
            patch("jd_manager.save_application_status") as save,
        ):
            applied = em.apply_updates(proposals, include_confirmed=True)

        self.assertEqual(applied, 1)
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
