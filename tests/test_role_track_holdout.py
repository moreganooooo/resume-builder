"""Tests for the IC-vs-manager labeling holdout sampler.

The holdout is the only thing that will make the >=90%-precision bar in
the role-attribute spec measurable, so the properties that keep it honest
-- blindness, stratification, and never destroying hand-labeling -- are
worth asserting rather than assuming.
"""

import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import build_role_track_holdout as holdout  # noqa: E402


class TestDescriptionExtraction(unittest.TestCase):
    def test_json_blob_yields_only_the_description(self):
        """raw_text is the whole JD document, not text.

        Persisted metadata reaching a labeler is the same hazard
        jd_manager.read_jd_text() prevents before a prompt.
        """
        stored = (
            '{"job_title": "Analyst", "description": "<p>Own the roadmap.</p>",'
            ' "_evaluation": {"composite_score": 88.5}}'
        )
        body = holdout._description_of(stored)
        self.assertEqual(body, "Own the roadmap.")
        self.assertNotIn("88.5", body)
        self.assertNotIn("_evaluation", body)

    def test_plain_text_passes_through(self):
        self.assertEqual(holdout._description_of("Plain body text"), "Plain body text")

    def test_unparseable_blob_is_empty_not_raw_json(self):
        self.assertEqual(holdout._description_of("{not json"), "")

    def test_tags_become_spaces_so_phrases_stay_matchable(self):
        """Welding list items together would break \\b-anchored matching."""
        body = holdout._strip_html("<li>direct reports</li><li>Manage a team</li>")
        self.assertNotIn("reportsManage", body)
        self.assertTrue(holdout.REPORTS_EVIDENCE.search(body))

    def test_entities_are_unescaped(self):
        self.assertEqual(holdout._strip_html("<p>R&amp;D team</p>"), "R&D team")


class TestStrata(unittest.TestCase):
    def test_title_signal_without_body_evidence(self):
        self.assertEqual(
            holdout._stratum("Marketing Manager", "Write copy and ship campaigns."),
            "title-only",
        )

    def test_title_and_body_together(self):
        self.assertEqual(
            holdout._stratum("Marketing Manager", "You will have 3 direct reports."),
            "title+body",
        )

    def test_ic_title_with_real_reports_described(self):
        """The inverse case a title-only heuristic would miss entirely."""
        self.assertEqual(
            holdout._stratum("Senior Copywriter", "You will manage a team of writers."),
            "body-only",
        )

    def test_neither(self):
        self.assertEqual(
            holdout._stratum("Content Strategist", "Write and edit articles."),
            "neither",
        )


class TestSampling(unittest.TestCase):
    def _rows(self):
        rows = []
        for stratum in ("title-only", "title+body", "neither"):
            for i in range(25):
                rows.append(
                    {
                        "job_id": f"{stratum}-{i}",
                        "title": "t",
                        "company": "c",
                        "stratum": stratum,
                        "excerpt": "e",
                    }
                )
        return rows

    def test_each_stratum_is_capped_independently(self):
        picked = holdout.sample(self._rows(), per_stratum=10, seed=0)
        counts: dict[str, int] = {}
        for row in picked:
            counts[row["stratum"]] = counts.get(row["stratum"], 0) + 1
        self.assertEqual(counts, {"title-only": 10, "title+body": 10, "neither": 10})

    def test_small_stratum_is_not_padded_from_others(self):
        rows = [r for r in self._rows() if r["stratum"] != "neither"]
        rows.append(
            {
                "job_id": "solo",
                "title": "t",
                "company": "c",
                "stratum": "body-only",
                "excerpt": "e",
            }
        )
        picked = holdout.sample(rows, per_stratum=10, seed=0)
        self.assertEqual(
            [r["job_id"] for r in picked if r["stratum"] == "body-only"], ["solo"]
        )

    def test_sampling_is_deterministic_for_a_seed(self):
        first = holdout.sample(self._rows(), 10, seed=3)
        second = holdout.sample(self._rows(), 10, seed=3)
        self.assertEqual([r["job_id"] for r in first], [r["job_id"] for r in second])

    def test_rows_are_not_grouped_by_stratum(self):
        """Ordered output lets a labeler pattern-match position, not read."""
        picked = holdout.sample(self._rows(), 25, seed=0)
        strata = [r["stratum"] for r in picked]
        runs = sum(1 for a, b in zip(strata, strata[1:]) if a != b)
        self.assertGreater(runs, 10)


class TestLabelNormalization(unittest.TestCase):
    """Real labeling produced "IC", "ic", and "unclear, likely IC"."""

    def test_case_is_ignored(self):
        self.assertEqual(holdout.normalize_label("IC"), "ic")
        self.assertEqual(holdout.normalize_label("  Manager "), "manager")

    def test_qualified_label_resolves_to_its_leading_term(self):
        """A hedge is uncertainty, not a second verdict.

        Scoring "unclear, likely IC" as "ic" would silently promote the
        labeler's doubt into a confident answer.
        """
        self.assertEqual(holdout.normalize_label("unclear, likely IC"), "unclear")

    def test_genuinely_unrecognized_is_empty(self):
        self.assertEqual(holdout.normalize_label("boss"), "")
        self.assertEqual(holdout.normalize_label(""), "")

    def test_not_applicable_is_a_verdict(self):
        """Some sampled roles have no IC/manager axis at all.

        The sample is drawn from the whole corpus, so it catches things
        like an in-person retail associate. Forcing one into "ic" to
        satisfy a three-value vocabulary puts a WRONG label in the ground
        truth the classifier is later measured against.
        """
        for spelling in ("n/a", "N/A", "na", "Not Applicable", "none"):
            with self.subTest(spelling=spelling):
                self.assertEqual(holdout.normalize_label(spelling), "n/a")

    def test_slash_labels_survive_the_qualifier_split(self):
        """The trap: "/" separates a qualifier AND lives inside "n/a".

        Splitting before checking the whole string silently yields "n",
        which is unrecognized, which reads as an unlabeled row -- so the
        label would vanish rather than fail loudly.
        """
        self.assertEqual(holdout.normalize_label("n/a"), "n/a")
        self.assertEqual(holdout.normalize_label("unclear/maybe ic"), "unclear")

    def test_spelled_out_labels_are_accepted(self):
        self.assertEqual(holdout.normalize_label("individual contributor"), "ic")
        self.assertEqual(holdout.normalize_label("people manager"), "manager")
        self.assertEqual(holdout.normalize_label("unsure"), "unclear")


class TestHoldoutFile(unittest.TestCase):
    def test_written_file_is_blind(self):
        """No prediction column: a labeler shown a guess agrees with it."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.csv")
            holdout.write_holdout(
                path,
                [
                    {
                        "job_id": "1",
                        "title": "Manager",
                        "company": "Acme",
                        "stratum": "title-only",
                        "excerpt": "text",
                    }
                ],
            )
            rows = list(csv.DictReader(open(path)))
        self.assertEqual(rows[0]["label"], "")
        for field in rows[0]:
            self.assertNotIn("predict", field.lower())
            self.assertNotIn("guess", field.lower())

    def test_status_flags_an_unrecognized_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.csv")
            with open(path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(
                    [
                        "job_id",
                        "title",
                        "company",
                        "stratum",
                        "label",
                        "note",
                        "excerpt",
                    ]
                )
                writer.writerow(["1", "t", "c", "neither", "ic", "", "e"])
                writer.writerow(["2", "t", "c", "neither", "boss", "", "e"])
            self.assertEqual(holdout.status(path), 1)

    def test_status_accepts_valid_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "h.csv")
            with open(path, "w", newline="") as fh:
                writer = csv.writer(fh)
                writer.writerow(
                    [
                        "job_id",
                        "title",
                        "company",
                        "stratum",
                        "label",
                        "note",
                        "excerpt",
                    ]
                )
                for value in holdout.LABEL_VALUES:
                    writer.writerow(["1", "t", "c", "neither", value, "", "e"])
            self.assertEqual(holdout.status(path), 0)


if __name__ == "__main__":
    unittest.main()
