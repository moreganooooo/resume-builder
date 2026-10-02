"""A skills category with one item is a layout defect with a deterministic fix.

Shipped on a real 2026-09-30 build: "Productivity: Microsoft Office Suite"
sat beside rows of six and eight items, while that profile's cv.md filed
eleven skills under Productivity -- the page was thin where the evidence
was not.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import orchestrator  # noqa: E402
import validate_resume  # noqa: E402

CV = """
## Core Skills

**Productivity:** Slack, Zoom, Trello, Microsoft Office, Google Workspace, Notion

**Creative & Design:** Figma, Photoshop, Illustrator, Canva

## Other Section

**Productivity:** Should Not Be Read
"""

STYLE = {"skills_section": {"line_max_chars": 110, "widow_min_chars": 25}}


def fill(lines, jd_keywords=None, cv=CV):
    return orchestrator._fill_thin_skill_categories(
        {"SKILLS": list(lines)}, STYLE, cv, jd_keywords or {}
    )


class TestThinCategoryCheck(unittest.TestCase):
    def test_single_item_category_is_flagged(self):
        violations = validate_resume._check_thin_skill_categories(
            {"SKILLS": ["**Productivity:** Microsoft Office Suite"]}
        )
        self.assertEqual(len(violations), 1)
        self.assertIn("Productivity", violations[0])

    def test_two_items_is_enough(self):
        self.assertEqual(
            validate_resume._check_thin_skill_categories(
                {"SKILLS": ["**Productivity:** Slack, Zoom"]}
            ),
            [],
        )

    def test_flag_is_soft_never_fatal(self):
        """A lonely row must not be able to fail a build."""
        violations = validate_resume._check_thin_skill_categories(
            {"SKILLS": ["**Productivity:** Microsoft Office Suite"]}
        )
        fatal, soft = orchestrator.partition_violations(violations)
        self.assertEqual(fatal, [])
        self.assertEqual(soft, violations)

    def test_wired_into_validate(self):
        """The check has to actually run, not just exist."""
        import inspect

        self.assertIn(
            "_check_thin_skill_categories",
            inspect.getsource(validate_resume.validate),
        )


class TestFillThinCategories(unittest.TestCase):
    def test_fills_from_the_rows_own_cv_group(self):
        result, added = fill(["**Productivity:** Microsoft Office"])
        self.assertEqual(len(added), 1)
        self.assertIn(
            added[0], ["Slack", "Zoom", "Trello", "Google Workspace", "Notion"]
        )
        self.assertEqual(validate_resume._check_thin_skill_categories(result), [])

    def test_matches_group_by_label_when_the_item_is_reworded(self):
        """The model renames items ("Microsoft Office Suite"), so the label
        has to be able to identify the group on its own."""
        _, added = fill(["**Productivity:** Microsoft Office Suite"])
        self.assertEqual(len(added), 1)

    def test_jd_matched_skills_are_added_first(self):
        _, added = fill(
            ["**Productivity:** Microsoft Office"], {"tools": ["Google Workspace"]}
        )
        self.assertEqual(added, ["Google Workspace"])

    def test_leaves_full_categories_alone(self):
        result, added = fill(["**Creative & Design:** Figma, Photoshop"])
        self.assertEqual(added, [])
        self.assertEqual(result["SKILLS"], ["**Creative & Design:** Figma, Photoshop"])

    def test_never_repeats_a_skill_already_on_the_page(self):
        result, added = fill(
            [
                "**Productivity:** Microsoft Office",
                "**Ops:** Slack, Zoom, Trello, Google Workspace, Notion",
            ]
        )
        items = [
            i
            for line in result["SKILLS"]
            for i in orchestrator._skill_line_items(line)[1]
        ]
        self.assertEqual(len(items), len(set(i.casefold() for i in items)))
        self.assertEqual(added, [])

    def test_skips_a_category_it_cannot_place(self):
        """Filling from the wrong group is worse than leaving a row thin."""
        result, added = fill(["**Quantum Widgetry:** Flux Capacitors"])
        self.assertEqual(added, [])
        self.assertEqual(result["SKILLS"], ["**Quantum Widgetry:** Flux Capacitors"])

    def test_skips_when_the_label_ties_between_groups(self):
        cv = (
            "## Core Skills\n\n"
            "**Design Systems:** Alpha, Beta\n\n"
            "**Design Tooling:** Gamma, Delta\n"
        )
        _, added = fill(["**Design:** Something Else"], cv=cv)
        self.assertEqual(added, [])

    def test_never_breaks_the_line_geometry(self):
        """An addition that lands in the widow dead band is refused."""
        long_item = "A" * 100
        result, added = fill([f"**Productivity:** {long_item}"])
        self.assertEqual(added, [])
        self.assertEqual(result["SKILLS"], [f"**Productivity:** {long_item}"])

    def test_does_not_mutate_its_input(self):
        original = {"SKILLS": ["**Productivity:** Microsoft Office"]}
        snapshot = list(original["SKILLS"])
        orchestrator._fill_thin_skill_categories(original, STYLE, CV, {})
        self.assertEqual(original["SKILLS"], snapshot)

    def test_no_cv_text_is_a_no_op(self):
        result, added = fill(["**Productivity:** Microsoft Office"], cv="")
        self.assertEqual(added, [])
        self.assertEqual(result["SKILLS"], ["**Productivity:** Microsoft Office"])


class TestCvSkillMembers(unittest.TestCase):
    def test_members_and_groups_agree(self):
        """Both readings come from one traversal, so they cannot disagree
        about which skills exist or where they belong."""
        members = orchestrator._parse_cv_skill_members(CV)
        groups = orchestrator._parse_cv_skill_groups(CV)
        for label, items in members.items():
            for item in items:
                self.assertEqual(groups.get(item.casefold()), label)
        self.assertEqual(
            sum(len(v) for v in members.values()),
            len(groups),
        )

    def test_reads_only_the_core_skills_block(self):
        members = orchestrator._parse_cv_skill_members(CV)
        self.assertNotIn("Should Not Be Read", members.get("Productivity", []))


if __name__ == "__main__":
    unittest.main()
