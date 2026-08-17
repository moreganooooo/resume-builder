import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402

SKILLS_RULES = {"skills_section": {"line_max_chars": 110, "widow_min_chars": 25}}
BULLET_RULES = {"bullet_structure": {"one_liner_max_chars": 108, "widow_min_words": 5}}


def _real_skills_widow_violation() -> str:
    # 120 chars -> inside the 111-134 dead band.
    return validate_resume._check_skills_line_lengths(
        {"SKILLS": ["X" * 120]}, SKILLS_RULES
    )[0]


def _real_skills_third_line_violation() -> str:
    return validate_resume._check_skills_line_lengths(
        {"SKILLS": ["X" * 230]}, SKILLS_RULES
    )[0]


def _real_bullet_widow_violation() -> str:
    # 112 chars, so it wraps at 108 and strands a 1-word widow.
    resume = {
        "EXPERIENCE": [{"achievements": ["Shipped " + "x" * 99 + " thing extra"]}]
    }
    violations = validate_resume._check_bullet_widows(resume, BULLET_RULES)
    assert violations, "fixture no longer produces a bullet-widow violation"
    return violations[0]


class TestRetryHintGuardsMatchRealValidatorOutput(unittest.TestCase):
    """The retry-hint blocks in build_tailored_resume are selected by
    matching validator message text. That couples two files through a
    prose string with nothing to catch a drift -- the block just silently
    stops being injected. These pin the contract to real validator output
    rather than to a hardcoded copy of the message."""

    def test_skills_guard_matches_a_real_widow_violation(self):
        self.assertTrue(
            orchestrator._is_skills_line_violation(_real_skills_widow_violation())
        )

    def test_skills_guard_matches_a_real_third_line_violation(self):
        self.assertTrue(
            orchestrator._is_skills_line_violation(_real_skills_third_line_violation())
        )

    def test_bullet_guard_matches_a_real_bullet_widow_violation(self):
        self.assertTrue(
            orchestrator._is_bullet_widow_violation(_real_bullet_widow_violation())
        )

    def test_skills_guard_ignores_unrelated_violations(self):
        self.assertFalse(
            orchestrator._is_skills_line_violation("Bullet is 300 chars and exceeds")
        )


class TestMetricInventoryGate(unittest.TestCase):
    """Stays narrow on purpose. Firing on widow violations too was tried
    and reverted (2026-08-12): the inventory then landed on nearly every
    retry and the model started deleting bullets to dodge collisions,
    breaking the per-role minimums. Uniqueness is now a selection-time
    concern, not a retry-time repair."""

    def test_fires_on_an_existing_metric_violation(self):
        self.assertTrue(
            orchestrator._needs_metric_inventory(["Metric '100' is used in 2 bullets"])
        )

    def test_does_not_fire_on_a_widow_violation_alone(self):
        self.assertFalse(
            orchestrator._needs_metric_inventory([_real_skills_widow_violation()])
        )
        self.assertFalse(
            orchestrator._needs_metric_inventory([_real_bullet_widow_violation()])
        )

    def test_does_not_fire_on_unrelated_violations(self):
        self.assertFalse(
            orchestrator._needs_metric_inventory(
                ["Pronoun 'I' found outside the Why section"]
            )
        )


if __name__ == "__main__":
    unittest.main()
