import os
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import evidence_bank
import profile_paths


class TestEvidenceBank(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil

        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def test_load_and_save_behavioral_stories(self):
        story = evidence_bank.BehavioralStory(
            id="test_story",
            title="Test Story Title",
            archetype="Leadership",
            situation="High pressure deadline",
            task="Deliver roadmap",
            action="Automated test harness",
            result="100% on time",
            reflection_learning="Automation saves time",
            metrics=["100% on time"],
            tools_used=["Python", "Git"],
            tags=["leadership", "automation"],
            target_roles=["Staff Engineer"],
        )

        with profile_paths.isolate_for_tests(self.tmp_dir):
            evidence_bank.save_behavioral_stories([story], profile="test_user")
            loaded = evidence_bank.load_behavioral_stories(profile="test_user")

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].id, "test_story")
            self.assertEqual(loaded[0].archetype, "Leadership")
            self.assertEqual(loaded[0].metrics, ["100% on time"])

    def test_load_and_save_negotiation_levers(self):
        lever = evidence_bank.NegotiationLever(
            id="test_lever",
            category="Compensation",
            anchor_point="$170k Base",
            talking_point="My proven impact warrants this target.",
            metric_proof="Increased throughput by 25%.",
            counter_scenario="If base is lower, ask for equity.",
            trade_off_concession="Flexible on bonus timing.",
            priority="High",
        )

        with profile_paths.isolate_for_tests(self.tmp_dir):
            evidence_bank.save_negotiation_levers([lever], profile="test_user")
            loaded = evidence_bank.load_negotiation_levers(profile="test_user")

            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].id, "test_lever")
            self.assertEqual(loaded[0].category, "Compensation")
            self.assertEqual(loaded[0].anchor_point, "$170k Base")

    def test_filter_stories_by_archetype_and_tag(self):
        s1 = evidence_bank.BehavioralStory(
            id="s1",
            title="Ops Story",
            archetype="ProblemSolving",
            situation="S",
            task="T",
            action="A",
            result="R",
            tags=["ops", "python"],
        )
        s2 = evidence_bank.BehavioralStory(
            id="s2",
            title="Lead Story",
            archetype="Leadership",
            situation="S",
            task="T",
            action="A",
            result="R",
            tags=["lead", "strategy"],
        )

        stories = [s1, s2]
        self.assertEqual(
            len(evidence_bank.filter_stories(stories, archetype="Leadership")), 1
        )
        self.assertEqual(len(evidence_bank.filter_stories(stories, tag="python")), 1)
        self.assertEqual(len(evidence_bank.filter_stories(stories, query="Ops")), 1)

    def test_filter_negotiation_levers_by_category_and_query(self):
        l1 = evidence_bank.NegotiationLever(
            id="l1",
            category="Compensation",
            anchor_point="$170k",
            talking_point="Comp anchor",
            metric_proof="Metrics",
        )
        l2 = evidence_bank.NegotiationLever(
            id="l2",
            category="RemoteFlexibility",
            anchor_point="100% Remote",
            talking_point="Distributed work",
            metric_proof="Metrics",
        )

        levers = [l1, l2]
        self.assertEqual(
            len(evidence_bank.filter_negotiation_levers(levers, category="Remote")), 1
        )
        self.assertEqual(
            len(evidence_bank.filter_negotiation_levers(levers, query="Comp")), 1
        )

    def test_empty_and_corrupt_files(self):
        with profile_paths.isolate_for_tests(self.tmp_dir):
            # Missing files return empty list
            self.assertEqual(evidence_bank.load_behavioral_stories("test_user"), [])
            self.assertEqual(evidence_bank.load_negotiation_levers("test_user"), [])

            # Corrupt file handles gracefully
            p = evidence_bank.stories_file_path("test_user")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write("{invalid json")
            self.assertEqual(evidence_bank.load_behavioral_stories("test_user"), [])


if __name__ == "__main__":
    unittest.main()
