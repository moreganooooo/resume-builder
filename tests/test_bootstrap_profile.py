import csv
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import bootstrap_bullet_bank  # noqa: E402
import bootstrap_extractors  # noqa: E402
import bootstrap_profile  # noqa: E402
import situational_roles  # noqa: E402
import yaml  # noqa: E402


class BootstrapProfileTestCase(unittest.TestCase):
    """Redirects every relevant path constant to a fresh temp dir per test."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.bootstrap_dir = os.path.join(self.tmp_dir, "bootstrap")
        bootstrap_bullet_bank.BOOTSTRAP_DIR = self.bootstrap_dir
        bootstrap_bullet_bank.SOURCE_DOCS_DIR = os.path.join(
            self.bootstrap_dir, "source_documents"
        )
        bootstrap_bullet_bank.TIMELINE_PATH = os.path.join(
            self.bootstrap_dir, "timeline.json"
        )
        bootstrap_bullet_bank.CHECKPOINT_PATH = os.path.join(
            self.bootstrap_dir, "checkpoint.json"
        )
        bootstrap_bullet_bank.DRAFT_CSV_PATH = os.path.join(
            self.bootstrap_dir, "bullet-bank-draft.csv"
        )
        os.makedirs(bootstrap_bullet_bank.SOURCE_DOCS_DIR, exist_ok=True)

        bootstrap_profile.PROFILE_YML_PATH = os.path.join(self.tmp_dir, "profile.yml")
        bootstrap_profile.PORTALS_YML_PATH = os.path.join(self.tmp_dir, "portals.yml")
        bootstrap_profile.SITUATIONAL_ROLES_PATH = os.path.join(
            self.tmp_dir, "situational_roles.yaml"
        )
        bootstrap_profile.CV_MD_PATH = os.path.join(self.tmp_dir, "cv.md")
        bootstrap_profile.BACKGROUND_GUIDE_PATH = os.path.join(
            self.tmp_dir, "user-background-guide.md"
        )
        bootstrap_profile.VOICE_ANCHORS_PATH = os.path.join(
            self.tmp_dir, "voice-anchors.md"
        )
        bootstrap_profile.VERIFIED_METRICS_PATH = os.path.join(
            self.tmp_dir, "verified_metrics.json"
        )
        bootstrap_profile.VERIFIED_TOOLS_PATH = os.path.join(
            self.tmp_dir, "verified_tools.json"
        )
        bootstrap_profile.VERIFIED_PROJECTS_PATH = os.path.join(
            self.tmp_dir, "verified_projects.json"
        )
        bootstrap_profile.VERIFIED_FACTS_PATH = os.path.join(
            self.tmp_dir, "verified_facts.json"
        )
        bootstrap_profile.VERIFIED_CLAIMS_PATH = os.path.join(
            self.tmp_dir, "verified-claims.csv"
        )
        bootstrap_profile.EVIDENCE_GRAPH_PATH = os.path.join(
            self.tmp_dir, "evidence_graph.json"
        )
        bootstrap_profile.EVIDENCE_GUIDE_PATH = os.path.join(
            self.tmp_dir, "evidence-guide.csv"
        )
        bootstrap_profile.SCREENSHOT_METRICS_PATH = os.path.join(
            self.tmp_dir, "extracted-screenshot-metrics.csv"
        )
        bootstrap_profile.RECRUITER_PATTERNS_PATH = os.path.join(
            self.tmp_dir, "recruiter_memory_patterns.json"
        )
        bootstrap_profile.CV_DRAFT_CHECKPOINT_PATH = os.path.join(
            self.bootstrap_dir, "cv_draft_checkpoint.json"
        )

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_checkpoint(self, data: dict) -> None:
        with open(bootstrap_bullet_bank.CHECKPOINT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _write_timeline(self, entries: list) -> None:
        with open(bootstrap_bullet_bank.TIMELINE_PATH, "w", encoding="utf-8") as f:
            json.dump(entries, f)

    def _touch_source(self, filename: str) -> None:
        with open(
            os.path.join(bootstrap_bullet_bank.SOURCE_DOCS_DIR, filename),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("placeholder")


class TestBuildCvDraftRows(BootstrapProfileTestCase):
    """Regression coverage: a company with more than one timeline entry
    (two real stints at the same employer) used to attach its WHOLE
    bullet pool to every entry for that company, rendering the same
    achievements twice on cv.md -- once per stint. Confirmed live on a
    real profile after normalizing "mIQroTech"/"mIQroTech Inc." spelling
    variants to one canonical name: both of its two timeline entries
    (2018-2019 and 2021-2022) started reporting the same 87 bullets."""

    def _write_draft_csv(self, rows: list) -> None:
        with open(
            bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(f, fieldnames=["Role / Company", "Bullet Point"])
            writer.writeheader()
            writer.writerows(rows)

    def test_second_stint_at_same_company_does_not_duplicate_bullets(self):
        self._write_timeline(
            [
                {
                    "company": "Acme Corp",
                    "title": "Data Scientist",
                    "start_date": "2018",
                    "end_date": "2019",
                },
                {
                    "company": "Acme Corp",
                    "title": "Lead Data Scientist",
                    "start_date": "2021",
                    "end_date": "2022",
                },
            ]
        )
        self._write_draft_csv(
            [
                {"Role / Company": "Acme Corp", "Bullet Point": "Did thing one"},
                {"Role / Company": "Acme Corp", "Bullet Point": "Did thing two"},
            ]
        )
        rows = bootstrap_profile._build_cv_draft_rows()
        acme_rows = [r for r in rows if r["company"] == "Acme Corp"]
        self.assertEqual(len(acme_rows), 2)

        # Sorted by end_date descending -- the 2021-2022 stint comes first
        # and gets the bullet pool; the 2018-2019 stint gets none rather
        # than a duplicate copy.
        self.assertEqual(acme_rows[0]["title"], "Lead Data Scientist")
        self.assertEqual(acme_rows[0]["bullets"], ["Did thing one", "Did thing two"])
        self.assertEqual(acme_rows[1]["title"], "Data Scientist")
        self.assertEqual(acme_rows[1]["bullets"], [])

    def test_single_stint_companies_unaffected(self):
        self._write_timeline(
            [
                {
                    "company": "Acme Corp",
                    "title": "Data Scientist",
                    "start_date": "2018",
                    "end_date": "2019",
                },
                {
                    "company": "Other Co",
                    "title": "Analyst",
                    "start_date": "2019",
                    "end_date": "2021",
                },
            ]
        )
        self._write_draft_csv(
            [
                {"Role / Company": "Acme Corp", "Bullet Point": "Did thing one"},
                {"Role / Company": "Other Co", "Bullet Point": "Did thing two"},
            ]
        )
        rows = bootstrap_profile._build_cv_draft_rows()
        by_company = {r["company"]: r["bullets"] for r in rows}
        self.assertEqual(by_company["Acme Corp"], ["Did thing one"])
        self.assertEqual(by_company["Other Co"], ["Did thing two"])


class TestGuessContactInfo(BootstrapProfileTestCase):

    @patch("bootstrap_profile.bootstrap_extractors.extract_contact_info")
    def test_finds_info_from_resume_file(self, mock_extract):
        self._touch_source("resume.txt")
        self._write_checkpoint({"resume.txt": {"status": "done", "doc_type": "resume"}})
        mock_extract.return_value = bootstrap_extractors.ContactInfo(
            full_name="Jamie Rivera", email="jamie@example.com"
        )

        info = bootstrap_profile._guess_contact_info(
            bootstrap_profile._load_checkpoint()
        )

        self.assertEqual(info.full_name, "Jamie Rivera")

    def test_returns_blank_when_no_resume_file(self):
        self._write_checkpoint(
            {"notes.txt": {"status": "done", "doc_type": "achievement_notes"}}
        )
        info = bootstrap_profile._guess_contact_info(
            bootstrap_profile._load_checkpoint()
        )
        self.assertIsNone(info.full_name)


class TestGuessPrimaryRoles(unittest.TestCase):

    def test_returns_recent_titles_most_recent_first(self):
        timeline = [
            {
                "company": "Old Co",
                "title": "Coordinator",
                "start_date": "2015",
                "end_date": "2018",
            },
            {
                "company": "Acme Corp",
                "title": "Marketing Manager",
                "start_date": "2019",
                "end_date": "2022",
            },
        ]
        roles = bootstrap_profile._guess_primary_roles(timeline)
        self.assertEqual(roles[0], "Marketing Manager")


class TestGuessRecommendations(BootstrapProfileTestCase):

    @patch("bootstrap_profile.bootstrap_extractors.extract_recommendation_quote")
    def test_collects_quotes_from_recommendation_letters(self, mock_extract):
        self._touch_source("letter.txt")
        self._write_checkpoint(
            {"letter.txt": {"status": "done", "doc_type": "recommendation_letter"}}
        )
        mock_extract.return_value = bootstrap_extractors.RecommendationQuote(
            name="Alex Chen", title="VP Marketing", quote="Excellent writer."
        )

        quotes = bootstrap_profile._guess_recommendations(
            bootstrap_profile._load_checkpoint()
        )

        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].name, "Alex Chen")

    def test_returns_empty_list_when_no_recommendation_letters(self):
        self._write_checkpoint({"resume.txt": {"status": "done", "doc_type": "resume"}})
        quotes = bootstrap_profile._guess_recommendations(
            bootstrap_profile._load_checkpoint()
        )
        self.assertEqual(quotes, [])


class TestCollectIdentityDryRun(BootstrapProfileTestCase):

    def test_dry_run_returns_guesses_without_prompting(self):
        self._write_timeline(
            [
                {
                    "company": "Acme Corp",
                    "title": "Marketing Manager",
                    "start_date": "2019",
                    "end_date": "2022",
                }
            ]
        )
        self._write_checkpoint({})

        with (
            patch("bootstrap_profile.questionary.text") as mock_text,
            patch("bootstrap_profile.questionary.checkbox") as mock_checkbox,
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
        ):
            identity = bootstrap_profile.collect_identity(dry_run=True)
            mock_text.assert_not_called()
            mock_checkbox.assert_not_called()
            mock_confirm.assert_not_called()

        self.assertEqual(identity["primary_roles"], ["Marketing Manager"])
        self.assertEqual(identity["secondary_roles"], [])


class TestCollectIdentityReviewAndRedo(BootstrapProfileTestCase):
    """Regression coverage for the review-and-redo loop: collect_identity()
    used to commit all 9 sequential answers with no way to correct an
    earlier one short of finishing the whole wizard and re-running this
    step from scratch. Primary/secondary roles are kept empty on both
    passes in these tests specifically so _confirm_roles() stays on its
    "no guessed roles" (text-only) branch on every pass -- a non-empty
    result would flip it to the checkbox branch on the next pass, which is
    exercised separately elsewhere."""

    def _blank_checkpoint_and_timeline(self):
        self._write_timeline([])
        self._write_checkpoint({})

    def test_confirming_first_pass_returns_immediately(self):
        self._blank_checkpoint_and_timeline()
        with (
            patch("bootstrap_profile.questionary.text") as mock_text,
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
        ):
            mock_text.return_value.ask.side_effect = [
                "Jamie Rivera",  # full name
                "jamie@example.com",  # email
                "555-0001",  # phone
                "Austin, TX",  # location
                "linkedin.com/in/jamie",  # linkedin
                "",  # portfolio
                "",  # extra link
                "",  # primary roles (text-only branch, guessed empty)
                "",  # secondary roles (text-only branch, guessed empty)
            ]
            # remote-only confirm, then "Everything look right?"
            mock_confirm.return_value.ask.side_effect = [True, True]

            identity = bootstrap_profile.collect_identity()

        self.assertEqual(mock_text.call_count, 9)
        self.assertEqual(mock_confirm.call_count, 2)
        self.assertEqual(identity["full_name"], "Jamie Rivera")
        self.assertEqual(identity["email"], "jamie@example.com")

    def test_declining_review_reprompts_with_previous_answers_as_defaults(self):
        self._blank_checkpoint_and_timeline()
        with (
            patch("bootstrap_profile.questionary.text") as mock_text,
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
        ):
            mock_text.return_value.ask.side_effect = [
                # Pass 1 -- email has a typo.
                "Jamie Rivera",
                "jamie@wrong.com",
                "555-0001",
                "Austin, TX",
                "linkedin.com/in/jamie",
                "",
                "",
                "",
                "",
                # Pass 2 -- only email is corrected; everything else is
                # re-typed identically (a mocked .ask() ignores `default`,
                # it doesn't "press Enter" on its own, so the redo pass
                # still needs a value for every field).
                "Jamie Rivera",
                "jamie@example.com",
                "555-0001",
                "Austin, TX",
                "linkedin.com/in/jamie",
                "",
                "",
                "",
                "",
            ]
            # Pass 1: remote-only confirm, then decline the review.
            # Pass 2: remote-only confirm, then accept the review.
            mock_confirm.return_value.ask.side_effect = [True, False, True, True]

            identity = bootstrap_profile.collect_identity()

        self.assertEqual(mock_text.call_count, 18)
        self.assertEqual(mock_confirm.call_count, 4)
        self.assertEqual(identity["email"], "jamie@example.com")

        # The redo pass's full_name prompt must default to pass 1's own
        # answer, not the original (blank) guess -- this is the actual
        # "previous answers are pre-filled" behavior, not just that a
        # second pass happened.
        pass_two_full_name_call = mock_text.call_args_list[9]
        self.assertEqual(pass_two_full_name_call.kwargs["default"], "Jamie Rivera")
        pass_two_email_call = mock_text.call_args_list[10]
        self.assertEqual(pass_two_email_call.kwargs["default"], "jamie@wrong.com")


class TestLoadExistingIdentity(BootstrapProfileTestCase):

    def test_returns_empty_dict_when_no_profile_yml(self):
        self.assertEqual(bootstrap_profile._load_existing_identity(), {})

    def test_reads_candidate_and_target_roles_from_existing_file(self):
        os.makedirs(os.path.dirname(bootstrap_profile.PROFILE_YML_PATH), exist_ok=True)
        with open(bootstrap_profile.PROFILE_YML_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "candidate": {
                        "full_name": "Jamie Rivera",
                        "email": "jamie@example.com",
                        "linkedin": "linkedin.com/in/jamierivera",
                    },
                    "target_roles": {
                        "primary": ["Marketing Manager"],
                        "secondary": ["Content Strategist"],
                    },
                    "location": {"remote_required": True},
                },
                f,
            )
        existing = bootstrap_profile._load_existing_identity()
        self.assertEqual(existing["full_name"], "Jamie Rivera")
        self.assertEqual(existing["linkedin_url"], "linkedin.com/in/jamierivera")
        self.assertEqual(existing["primary_roles"], ["Marketing Manager"])
        self.assertEqual(existing["secondary_roles"], ["Content Strategist"])
        self.assertTrue(existing["remote_preference"])

    def test_dry_run_identity_falls_back_to_existing_profile_when_no_fresh_guess(self):
        # No timeline/checkpoint content this run -- fresh extraction finds
        # nothing, so an existing profile.yml's values should surface
        # instead of leaving the field blank.
        os.makedirs(os.path.dirname(bootstrap_profile.PROFILE_YML_PATH), exist_ok=True)
        with open(bootstrap_profile.PROFILE_YML_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                {
                    "candidate": {"full_name": "Jamie Rivera"},
                    "target_roles": {"primary": ["Marketing Manager"]},
                },
                f,
            )
        self._write_timeline([])
        self._write_checkpoint({})

        identity = bootstrap_profile.collect_identity(dry_run=True)
        self.assertEqual(identity["full_name"], "Jamie Rivera")
        self.assertEqual(identity["primary_roles"], ["Marketing Manager"])


class TestRunProfileSetupTargets(BootstrapProfileTestCase):

    def test_only_writes_selected_targets(self):
        self._write_timeline([])
        self._write_checkpoint({})
        with (
            patch("bootstrap_profile.collect_identity") as mock_identity,
            patch("bootstrap_profile.write_profile_yml") as mock_write_profile,
            patch("bootstrap_profile.write_portals_yml"),
            patch("bootstrap_profile.write_situational_roles"),
            patch("bootstrap_profile.seed_scan_filters_from_target_roles"),
            patch("bootstrap_profile.write_verified_ledger"),
            patch("bootstrap_profile.write_background_guide") as mock_background,
            patch("bootstrap_profile.write_voice_anchors") as mock_voice_anchors,
            patch("bootstrap_profile.write_cv_md") as mock_cv_md,
            patch("bootstrap_profile.collect_linkedin_search_queries", return_value=[]),
            patch("bootstrap_profile._guess_recommendations", return_value=[]),
            patch(
                "bootstrap_profile.bootstrap_extractors.generate_tag_taxonomy"
            ) as mock_taxonomy,
            patch("bootstrap_profile.collect_situational_roles", return_value=[]),
            patch(
                "bootstrap_profile.collect_voice_calibration_example", return_value=""
            ),
        ):
            mock_identity.return_value = {
                "full_name": "Jamie Rivera",
                "primary_roles": [],
                "secondary_roles": [],
            }
            mock_taxonomy.return_value.tags = []

            bootstrap_profile.run_profile_setup(
                dry_run=False, targets={bootstrap_profile.PROFILE_TARGET_CV_MD}
            )

            mock_cv_md.assert_called_once()
            mock_write_profile.assert_not_called()
            mock_background.assert_not_called()
            mock_voice_anchors.assert_not_called()

    def test_defaults_to_all_targets_when_unspecified(self):
        self._write_timeline([])
        self._write_checkpoint({})
        with (
            patch("bootstrap_profile.collect_identity") as mock_identity,
            patch("bootstrap_profile.write_profile_yml") as mock_write_profile,
            patch("bootstrap_profile.write_portals_yml"),
            patch("bootstrap_profile.write_situational_roles"),
            patch("bootstrap_profile.seed_scan_filters_from_target_roles"),
            patch("bootstrap_profile.write_verified_ledger"),
            patch("bootstrap_profile.stage_candidate_facts", return_value=0),
            patch("bootstrap_profile.write_background_guide") as mock_background,
            patch("bootstrap_profile.write_voice_anchors"),
            patch("bootstrap_profile.write_cv_md") as mock_cv_md,
            patch("bootstrap_profile.collect_linkedin_search_queries", return_value=[]),
            patch("bootstrap_profile._guess_recommendations", return_value=[]),
            patch(
                "bootstrap_profile.bootstrap_extractors.generate_tag_taxonomy"
            ) as mock_taxonomy,
            patch("bootstrap_profile.collect_situational_roles", return_value=[]),
            patch(
                "bootstrap_profile.collect_voice_calibration_example", return_value=""
            ),
            patch("bootstrap_profile.collect_deal_breakers", return_value=[]),
            patch("bootstrap_profile.offer_settings_screens"),
            patch("bootstrap_profile.report_job_board_readiness"),
        ):
            mock_identity.return_value = {
                "full_name": "Jamie Rivera",
                "primary_roles": [],
                "secondary_roles": [],
            }
            mock_taxonomy.return_value.tags = []

            bootstrap_profile.run_profile_setup(dry_run=False, targets=None)

            mock_cv_md.assert_called_once()
            mock_write_profile.assert_called_once()
            mock_background.assert_called_once()


class TestCollectDealBreakers(BootstrapProfileTestCase):

    def test_dry_run_returns_empty_without_prompting(self):
        self.assertEqual(bootstrap_profile.collect_deal_breakers(dry_run=True), [])

    @patch("bootstrap_profile._confirm_roles", return_value=["No on-site required"])
    def test_delegates_to_confirm_roles(self, mock_confirm_roles):
        result = bootstrap_profile.collect_deal_breakers(dry_run=False)
        mock_confirm_roles.assert_called_once()
        self.assertEqual(result, ["No on-site required"])


class TestReportJobBoardReadiness(BootstrapProfileTestCase):

    def test_runs_without_error_on_bare_profile(self):
        # No .env, no .linkedin_cookie, no tracked_companies.yml -- every
        # source should report as needing setup except Indeed, and this
        # must not raise. dry_run=True so the interactive "discover
        # employers now?" offer (added when tracked_count == 0) doesn't
        # block on stdin.
        bootstrap_profile.report_job_board_readiness(dry_run=True)

    def test_dry_run_skips_discover_offer(self):
        with patch("bootstrap_profile.cli_art.confirm") as mock_confirm:
            bootstrap_profile.report_job_board_readiness(dry_run=True)
            mock_confirm.assert_not_called()

    @patch("discover_local_employers.append_entries", return_value="/tmp/backup.yml")
    @patch(
        "discover_local_employers.tracked_companies_path", return_value="/tmp/tc.yml"
    )
    @patch(
        "discover_local_employers.discover",
        return_value=[{"name": "Acme", "provider": "greenhouse", "postings": 3}],
    )
    @patch("bootstrap_profile.cli_art.confirm", side_effect=[True, True])
    def test_offers_and_tracks_discovered_employers_when_none_tracked(
        self, mock_confirm, mock_discover, mock_path, mock_append
    ):
        bootstrap_profile.report_job_board_readiness(dry_run=False)

        mock_discover.assert_called_once()
        mock_append.assert_called_once_with(
            [{"name": "Acme", "provider": "greenhouse", "postings": 3}], "/tmp/tc.yml"
        )


class TestWriteProfileYml(BootstrapProfileTestCase):

    def test_writes_candidate_and_target_roles(self):
        import yaml

        identity = {
            "full_name": "Jamie Rivera",
            "email": "jamie@example.com",
            "phone": "555-0100",
            "location": "Austin, TX",
            "linkedin_url": "linkedin.com/in/jamierivera",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": ["Marketing Manager"],
            "secondary_roles": ["Customer Education Specialist"],
            "remote_preference": True,
        }

        bootstrap_profile.write_profile_yml(
            identity, recommendations=[], taxonomy=bootstrap_extractors.TagTaxonomy()
        )

        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["candidate"]["full_name"], "Jamie Rivera")
        self.assertEqual(data["target_roles"]["primary"], ["Marketing Manager"])
        self.assertEqual(
            data["target_roles"]["secondary"], ["Customer Education Specialist"]
        )
        self.assertEqual(data["location"]["remote_required"], True)

    def test_writes_generated_tags(self):
        import yaml

        identity = {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": [],
            "secondary_roles": [],
            "remote_preference": False,
        }
        taxonomy = bootstrap_extractors.TagTaxonomy(
            tags=[
                bootstrap_extractors.TagDefinition(
                    name="ops",
                    persona_description="operations or process roles",
                    keywords=["salesforce", "crm"],
                ),
                bootstrap_extractors.TagDefinition(
                    name="generalist", persona_description="general roles", keywords=[]
                ),
            ]
        )

        bootstrap_profile.write_profile_yml(
            identity, recommendations=[], taxonomy=taxonomy
        )

        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["tags"][0]["name"], "ops")
        self.assertEqual(data["tags"][0]["keywords"], ["salesforce", "crm"])
        self.assertEqual(data["tags"][1]["name"], "generalist")
        self.assertEqual(data["tags"][1]["keywords"], [])

    def test_auto_fills_key_recommendations_when_present(self):
        import yaml

        identity = {
            "full_name": "Jamie Rivera",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": [],
            "secondary_roles": [],
            "remote_preference": False,
        }
        recs = [
            bootstrap_extractors.RecommendationQuote(
                name="Alex Chen", title="VP Marketing", quote="Excellent writer."
            )
        ]

        bootstrap_profile.write_profile_yml(
            identity, recommendations=recs, taxonomy=bootstrap_extractors.TagTaxonomy()
        )

        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["key_recommendations"][0]["name"], "Alex Chen")
        self.assertEqual(data["key_recommendations"][0]["quote"], "Excellent writer.")

    def test_scaffolds_deep_sections_empty(self):
        import yaml

        identity = {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": [],
            "secondary_roles": [],
            "remote_preference": False,
        }
        bootstrap_profile.write_profile_yml(
            identity, recommendations=[], taxonomy=bootstrap_extractors.TagTaxonomy()
        )
        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["narrative"]["headline"], "")
        self.assertEqual(data["deal_breakers"], [""])
        self.assertEqual(data["management_evidence"], [])

    def _minimal_identity(self):
        return {
            "full_name": "Jamie Rivera",
            "email": "jamie@example.com",
            "phone": "555-0100",
            "location": "Austin, TX",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": ["Marketing Manager"],
            "secondary_roles": [],
            "remote_preference": True,
        }

    def test_no_confirm_prompt_when_no_existing_file(self):
        # Regression guard for the "Update My Knowledge" overwrite gate --
        # confirms a first-time cold start (no profile.yml yet) never
        # prompts, since there's nothing to lose.
        with patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            bootstrap_profile.write_profile_yml(
                self._minimal_identity(),
                recommendations=[],
                taxonomy=bootstrap_extractors.TagTaxonomy(),
            )
        mock_confirm.assert_not_called()
        self.assertTrue(os.path.exists(bootstrap_profile.PROFILE_YML_PATH))

    def test_declining_overwrite_leaves_existing_file_untouched_and_returns_false(self):
        with open(bootstrap_profile.PROFILE_YML_PATH, "w", encoding="utf-8") as f:
            f.write("candidate:\n  full_name: Original Name\n")

        with patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = False
            result = bootstrap_profile.write_profile_yml(
                self._minimal_identity(),
                recommendations=[],
                taxonomy=bootstrap_extractors.TagTaxonomy(),
            )

        self.assertFalse(result)
        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Original Name", content)

    def test_accepting_overwrite_replaces_the_file_and_returns_true(self):
        with open(bootstrap_profile.PROFILE_YML_PATH, "w", encoding="utf-8") as f:
            f.write("candidate:\n  full_name: Original Name\n")

        with patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = True
            result = bootstrap_profile.write_profile_yml(
                self._minimal_identity(),
                recommendations=[],
                taxonomy=bootstrap_extractors.TagTaxonomy(),
            )

        self.assertTrue(result)
        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Jamie Rivera", content)
        self.assertNotIn("Original Name", content)


class TestWritePortalsYml(BootstrapProfileTestCase):

    def test_seeds_title_filter_from_target_roles(self):
        import yaml

        identity = {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": ["Marketing Manager"],
            "secondary_roles": ["Customer Education Specialist"],
            "remote_preference": True,
        }

        bootstrap_profile.write_portals_yml(identity)

        with open(bootstrap_profile.PORTALS_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIn("Marketing Manager", data["title_filter"]["positive"])
        self.assertIn("Customer Education Specialist", data["title_filter"]["positive"])
        self.assertIn("Remote", data["location_filter"]["always_allow"])

    def test_scaffolds_block_and_seniority_boost_empty(self):
        import yaml

        identity = {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": [],
            "secondary_roles": [],
            "remote_preference": False,
        }
        bootstrap_profile.write_portals_yml(identity)
        with open(bootstrap_profile.PORTALS_YML_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["seniority_boost"], [])


class TestSeedScanFiltersFromTargetRoles(BootstrapProfileTestCase):

    def setUp(self):
        super().setUp()
        self.board_scanner_dir = os.path.join(self.tmp_dir, "board_scanner")
        os.makedirs(self.board_scanner_dir, exist_ok=True)
        self.scan_filters_path = os.path.join(
            self.board_scanner_dir, "scan_filters.yml"
        )
        patcher = patch(
            "bootstrap_profile.profile_paths.board_scanner_dir",
            return_value=self.board_scanner_dir,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _write_scaffold(
        self, positive=None, negative=None, always_allow=None, block=None
    ):
        import yaml

        data = {
            "title_filter": {"positive": positive or [], "negative": negative or []},
            "location_filter": {
                "always_allow": always_allow or ["Remote"],
                "block": block or [],
            },
        }
        with open(self.scan_filters_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f)

    def _identity(self, primary_roles, secondary_roles=None):
        return {
            "full_name": "",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": primary_roles,
            "secondary_roles": secondary_roles or [],
            "remote_preference": True,
        }

    def test_seeds_empty_scaffold_from_target_roles(self):
        import yaml

        self._write_scaffold()
        result = bootstrap_profile.seed_scan_filters_from_target_roles(
            self._identity(["Marketing Manager"], ["Customer Education Specialist"])
        )
        self.assertTrue(result)
        with open(self.scan_filters_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIn("Marketing Manager", data["title_filter"]["positive"])
        self.assertIn("Customer Education Specialist", data["title_filter"]["positive"])
        self.assertIn("Remote", data["location_filter"]["always_allow"])

    def test_does_not_overwrite_already_curated_filters(self):
        import yaml

        self._write_scaffold(positive=["Existing Title"])
        result = bootstrap_profile.seed_scan_filters_from_target_roles(
            self._identity(["New Role"])
        )
        self.assertFalse(result)
        with open(self.scan_filters_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["title_filter"]["positive"], ["Existing Title"])
        self.assertNotIn("New Role", data["title_filter"]["positive"])

    def test_does_not_overwrite_when_only_negative_is_curated(self):
        import yaml

        self._write_scaffold(negative=["Recruiter"])
        result = bootstrap_profile.seed_scan_filters_from_target_roles(
            self._identity(["New Role"])
        )
        self.assertFalse(result)
        with open(self.scan_filters_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["title_filter"]["negative"], ["Recruiter"])

    def test_noop_when_scaffold_missing(self):
        result = bootstrap_profile.seed_scan_filters_from_target_roles(
            self._identity(["New Role"])
        )
        self.assertFalse(result)
        self.assertFalse(os.path.exists(self.scan_filters_path))

    def test_preserves_other_top_level_keys_not_in_its_own_template(self):
        # Regression test: this used to rebuild the whole file from a
        # title_filter/location_filter-only template via a full atomic_write,
        # silently discarding any OTHER top-level key already present --
        # location: (commute radius), scoring_weights:, languages: -- the
        # moment this ran with an empty title_filter (e.g. "Update My
        # Knowledge" on a profile whose target roles were left blank, so
        # this keeps firing on every later run after Settings & Upkeep
        # configuration has already been added in between).
        self._write_scaffold()
        with open(self.scan_filters_path, "a", encoding="utf-8") as f:
            f.write(
                'location:\n  zip: "14068"\n  radius_miles: 10\n'
                "  workplace_mode: any\n"
                "languages:\n- en\n"
                "scoring_weights:\n  low_stress_bonus: 0.4\n"
            )

        result = bootstrap_profile.seed_scan_filters_from_target_roles(
            self._identity(["Marketing Manager"])
        )

        self.assertTrue(result)
        with open(self.scan_filters_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertIn("Marketing Manager", data["title_filter"]["positive"])
        self.assertEqual(data["location"]["zip"], "14068")
        self.assertEqual(data["languages"], ["en"])
        self.assertEqual(data["scoring_weights"]["low_stress_bonus"], 0.4)


class TestWriteVerifiedLedger(BootstrapProfileTestCase):

    @patch("bootstrap_profile.bootstrap_extractors.extract_ledger_entries_chunked")
    def test_derives_metrics_tools_projects_from_achievements(self, mock_extract):
        with open(
            bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Role / Company",
                    "Tags",
                    "Bullet Point",
                    "source_file",
                    "source_type",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Role / Company": "Acme Corp",
                    "Tags": "",
                    "Bullet Point": "- Grew reply rate to 22% using Outreach.io",
                    "source_file": "resume.txt",
                    "source_type": "resume",
                }
            )

        mock_extract.return_value = bootstrap_extractors.LedgerExtraction(
            metrics=[
                bootstrap_extractors.LedgerEntry(
                    label="Reply rate", value="22%", employer="Acme Corp"
                )
            ],
            tools=[
                bootstrap_extractors.NamedLedgerItem(
                    name="Outreach.io", employer="Acme Corp"
                )
            ],
            projects=[],
        )

        bootstrap_profile.write_verified_ledger()

        with open(bootstrap_profile.VERIFIED_METRICS_PATH, encoding="utf-8") as f:
            metrics = json.load(f)
        self.assertEqual(metrics["metrics"][0]["value"], "22%")
        self.assertEqual(metrics["metrics"][0]["employer"], "Acme Corp")
        with open(bootstrap_profile.VERIFIED_TOOLS_PATH, encoding="utf-8") as f:
            tools = json.load(f)
        self.assertEqual(tools["tools"][0]["name"], "Outreach.io")
        self.assertEqual(tools["tools"][0]["employer"], "Acme Corp")

    @patch("bootstrap_profile.bootstrap_extractors.extract_ledger_entries_chunked")
    def test_achievements_passed_to_extraction_are_tagged_with_employer(
        self, mock_extract
    ):
        # extract_ledger_entries() needs each bullet's employer visible in
        # the text it receives so it can attribute metrics/tools/projects
        # correctly -- without this, a fresh profile's verified_*.json
        # entries have no "employer" field and filter_projects_by_employer()
        # silently filters everything out.
        with open(
            bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Role / Company",
                    "Tags",
                    "Bullet Point",
                    "source_file",
                    "source_type",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Role / Company": "Acme Corp",
                    "Tags": "",
                    "Bullet Point": "- Grew reply rate to 22%",
                    "source_file": "resume.txt",
                    "source_type": "resume",
                }
            )

        mock_extract.return_value = bootstrap_extractors.LedgerExtraction()
        bootstrap_profile.write_verified_ledger()

        sent_text = mock_extract.call_args[0][0]
        self.assertIn("[Acme Corp]", sent_text)
        self.assertIn("Grew reply rate to 22%", sent_text)

    def test_scaffolds_cross_source_files_empty(self):
        bootstrap_profile.write_verified_ledger(dry_run=True)

        with open(bootstrap_profile.VERIFIED_FACTS_PATH, encoding="utf-8") as f:
            facts = json.load(f)
        self.assertEqual(facts["facts"], [])

        with open(bootstrap_profile.EVIDENCE_GRAPH_PATH, encoding="utf-8") as f:
            graph = json.load(f)
        self.assertEqual(graph["nodes"], [])

        with open(bootstrap_profile.VERIFIED_CLAIMS_PATH, encoding="utf-8") as f:
            header = f.readline().strip()
        self.assertEqual(
            header,
            "Claim / Finding,Verification Status,Source File,Evidence / Detail,Metric(s),Confidence,Use in Resume?,Use in Portfolio?,Next Follow-Up",
        )

        with open(bootstrap_profile.RECRUITER_PATTERNS_PATH, encoding="utf-8") as f:
            patterns = json.load(f)
        self.assertEqual(patterns["patterns"], [])


class TestWriteCvMd(BootstrapProfileTestCase):

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch(
        "bootstrap_profile.build_system_prompts",
        return_value=("rewrite sys", "rewrite sys gemma", "score sys"),
    )
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_accept_writes_header_and_per_role_sections(
        self,
        mock_rules_cls,
        mock_kb_cls,
        mock_build_prompts,
        mock_process_bullet,
        mock_select,
    ):
        self._write_timeline(
            [
                {
                    "company": "Acme Corp",
                    "title": "Marketing Manager",
                    "start_date": "2019",
                    "end_date": "2022",
                    "needs_review": False,
                    "conflict_note": None,
                },
            ]
        )
        with open(
            bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Role / Company",
                    "Tags",
                    "Bullet Point",
                    "source_file",
                    "source_type",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Role / Company": "Acme Corp",
                    "Tags": "",
                    "Bullet Point": "- Grew email list by 40%",
                    "source_file": "resume.txt",
                    "source_type": "resume",
                }
            )

        mock_process_bullet.return_value = {
            "final_bullet": "Grew the email list by 40% through segmentation."
        }
        mock_select.return_value.ask.return_value = "accept"

        identity = {
            "full_name": "Jamie Rivera",
            "email": "jamie@example.com",
            "phone": "",
            "location": "Austin, TX",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": [],
            "secondary_roles": [],
            "remote_preference": False,
        }

        bootstrap_profile.write_cv_md(identity)

        with open(bootstrap_profile.CV_MD_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Jamie Rivera", content)
        self.assertIn("Marketing Manager", content)
        self.assertIn("Acme Corp", content)
        self.assertIn("Grew the email list by 40% through segmentation.", content)
        mock_process_bullet.assert_called_once()

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch(
        "bootstrap_profile.build_system_prompts",
        return_value=("rewrite sys", "rewrite sys gemma", "score sys"),
    )
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_builds_rules_and_kb_once_not_per_bullet(
        self,
        mock_rules_cls,
        mock_kb_cls,
        mock_build_prompts,
        mock_process_bullet,
        mock_select,
    ):
        self._write_timeline(
            [
                {
                    "company": "Acme Corp",
                    "title": "Manager",
                    "start_date": "2019",
                    "end_date": "2022",
                    "needs_review": False,
                    "conflict_note": None,
                }
            ]
        )
        with open(
            bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Role / Company",
                    "Tags",
                    "Bullet Point",
                    "source_file",
                    "source_type",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Role / Company": "Acme Corp",
                    "Tags": "",
                    "Bullet Point": "- First bullet",
                    "source_file": "resume.txt",
                    "source_type": "resume",
                }
            )
            writer.writerow(
                {
                    "Role / Company": "Acme Corp",
                    "Tags": "",
                    "Bullet Point": "- Second bullet",
                    "source_file": "resume.txt",
                    "source_type": "resume",
                }
            )

        mock_process_bullet.return_value = {"final_bullet": "polished"}
        mock_select.return_value.ask.return_value = "accept"
        identity = {
            "full_name": "Jamie",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": [],
            "secondary_roles": [],
            "remote_preference": False,
        }

        bootstrap_profile.write_cv_md(identity)

        self.assertEqual(mock_rules_cls.call_count, 1)
        self.assertEqual(mock_kb_cls.call_count, 1)
        self.assertEqual(mock_process_bullet.call_count, 2)

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch(
        "bootstrap_profile.build_system_prompts",
        return_value=("rewrite sys", "rewrite sys gemma", "score sys"),
    )
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_skip_writes_empty_file(
        self,
        mock_rules_cls,
        mock_kb_cls,
        mock_build_prompts,
        mock_process_bullet,
        mock_select,
    ):
        self._write_timeline(
            [
                {
                    "company": "Acme Corp",
                    "title": "Manager",
                    "start_date": "2019",
                    "end_date": "2022",
                    "needs_review": False,
                    "conflict_note": None,
                }
            ]
        )
        with open(
            bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Role / Company",
                    "Tags",
                    "Bullet Point",
                    "source_file",
                    "source_type",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Role / Company": "Acme Corp",
                    "Tags": "",
                    "Bullet Point": "- First bullet",
                    "source_file": "resume.txt",
                    "source_type": "resume",
                }
            )

        mock_process_bullet.return_value = {"final_bullet": "polished"}
        mock_select.return_value.ask.return_value = "skip"
        identity = {
            "full_name": "Jamie",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": [],
            "secondary_roles": [],
            "remote_preference": False,
        }

        bootstrap_profile.write_cv_md(identity)

        with open(bootstrap_profile.CV_MD_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "")

    def test_dry_run_writes_without_prompting(self):
        with (
            patch("bootstrap_profile.questionary.select") as mock_select,
            patch("bootstrap_profile.RulesBundle"),
            patch("bootstrap_profile.KnowledgeBase"),
            patch(
                "bootstrap_profile.build_system_prompts",
                return_value=("rewrite sys", "rewrite sys gemma", "score sys"),
            ),
            patch(
                "bootstrap_profile.process_bullet",
                return_value={"final_bullet": "polished"},
            ),
        ):
            identity = {
                "full_name": "Jamie",
                "email": "",
                "phone": "",
                "location": "",
                "linkedin_url": "",
                "portfolio_url": "",
                "extra_link": "",
                "primary_roles": [],
                "secondary_roles": [],
                "remote_preference": False,
            }
            bootstrap_profile.write_cv_md(identity, dry_run=True)
            mock_select.assert_not_called()
        self.assertTrue(os.path.exists(bootstrap_profile.CV_MD_PATH))


class TestCvDraftResumability(BootstrapProfileTestCase):
    """
    Regression tests for write_cv_md()'s resumability: previously, an
    interruption mid-loop (network blip, closed terminal, laptop sleep)
    lost every bullet already polished -- up to 3 API calls each -- with
    no way to pick back up except starting completely over. Bullets are
    now checkpointed as they complete (mirroring bootstrap_bullet_bank.py's
    own Phase 0 checkpoint pattern), so a second call reuses prior work
    instead of re-polishing everything.
    """

    def _setup_one_bullet(self):
        self._write_timeline(
            [
                {
                    "company": "Acme Corp",
                    "title": "Manager",
                    "start_date": "2019",
                    "end_date": "2022",
                    "needs_review": False,
                    "conflict_note": None,
                }
            ]
        )
        with open(
            bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", newline="", encoding="utf-8"
        ) as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "Role / Company",
                    "Tags",
                    "Bullet Point",
                    "source_file",
                    "source_type",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "Role / Company": "Acme Corp",
                    "Tags": "",
                    "Bullet Point": "- First bullet",
                    "source_file": "resume.txt",
                    "source_type": "resume",
                }
            )
        return {
            "full_name": "Jamie",
            "email": "",
            "phone": "",
            "location": "",
            "linkedin_url": "",
            "portfolio_url": "",
            "extra_link": "",
            "primary_roles": [],
            "secondary_roles": [],
            "remote_preference": False,
        }

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch(
        "bootstrap_profile.build_system_prompts",
        return_value=("rewrite sys", "rewrite sys gemma", "score sys"),
    )
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_a_polished_bullet_is_checkpointed_to_disk(
        self,
        mock_rules_cls,
        mock_kb_cls,
        mock_build_prompts,
        mock_process_bullet,
        mock_select,
    ):
        identity = self._setup_one_bullet()
        mock_process_bullet.return_value = {
            "final_bullet": "polished",
            "rewrite_status": "KEEP",
        }
        mock_select.return_value.ask.return_value = "skip"

        bootstrap_profile.write_cv_md(identity)

        self.assertTrue(os.path.exists(bootstrap_profile.CV_DRAFT_CHECKPOINT_PATH))
        with open(bootstrap_profile.CV_DRAFT_CHECKPOINT_PATH, encoding="utf-8") as f:
            checkpoint = json.load(f)
        self.assertEqual(
            checkpoint["Acme Corp::- First bullet"]["final_bullet"], "polished"
        )

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch(
        "bootstrap_profile.build_system_prompts",
        return_value=("rewrite sys", "rewrite sys gemma", "score sys"),
    )
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_a_second_run_reuses_the_checkpoint_instead_of_recalling_the_api(
        self,
        mock_rules_cls,
        mock_kb_cls,
        mock_build_prompts,
        mock_process_bullet,
        mock_select,
    ):
        identity = self._setup_one_bullet()
        mock_process_bullet.return_value = {
            "final_bullet": "polished",
            "rewrite_status": "KEEP",
        }
        mock_select.return_value.ask.return_value = "skip"

        bootstrap_profile.write_cv_md(
            identity
        )  # first "run" -- polishes and checkpoints
        bootstrap_profile.write_cv_md(
            identity
        )  # simulated resume after an interruption

        mock_process_bullet.assert_called_once()  # not called again on the second run

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch(
        "bootstrap_profile.build_system_prompts",
        return_value=("rewrite sys", "rewrite sys gemma", "score sys"),
    )
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_regenerate_clears_the_checkpoint_and_recalls_the_api(
        self,
        mock_rules_cls,
        mock_kb_cls,
        mock_build_prompts,
        mock_process_bullet,
        mock_select,
    ):
        identity = self._setup_one_bullet()
        mock_process_bullet.return_value = {
            "final_bullet": "polished",
            "rewrite_status": "KEEP",
        }
        mock_select.return_value.ask.side_effect = ["regenerate", "skip"]

        bootstrap_profile.write_cv_md(identity)

        # regenerate is an explicit "start over" request -- it should not
        # silently replay the cached result from the draft just rejected.
        self.assertEqual(mock_process_bullet.call_count, 2)

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.process_bullet")
    @patch(
        "bootstrap_profile.build_system_prompts",
        return_value=("rewrite sys", "rewrite sys gemma", "score sys"),
    )
    @patch("bootstrap_profile.KnowledgeBase")
    @patch("bootstrap_profile.RulesBundle")
    def test_dry_run_never_writes_a_checkpoint_file(
        self,
        mock_rules_cls,
        mock_kb_cls,
        mock_build_prompts,
        mock_process_bullet,
        mock_select,
    ):
        # Regression test: a dry run must make zero real filesystem
        # changes, same guarantee as zero real API calls -- caught during
        # review before it ever wrote to a real profile's bootstrap/ dir,
        # since write_cv_md()'s dry_run branch still calls
        # _assemble_cv_draft() (to preview what *would* be drafted).
        identity = self._setup_one_bullet()
        mock_process_bullet.return_value = {
            "final_bullet": "[DRY RUN] polished",
            "rewrite_status": "MANUAL",
        }

        bootstrap_profile.write_cv_md(identity, dry_run=True)

        self.assertFalse(os.path.exists(bootstrap_profile.CV_DRAFT_CHECKPOINT_PATH))


class TestCollectSecrets(unittest.TestCase):
    """
    Regression tests for collect_secrets(): each profile now gets its own
    .env (profile_paths.env_path()) instead of one shared project-root
    file, and the wizard should never re-prompt for a var that's already
    set (this can run again on an existing profile, not just a brand-new
    one).
    """

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.env_path = os.path.join(self.tmp_dir, ".env")
        self._env_patch = patch(
            "bootstrap_profile.profile_paths.env_path", return_value=self.env_path
        )
        self._env_patch.start()
        self._orig_gemini = os.environ.pop("GEMINI_API_KEY", None)
        self._orig_google = os.environ.pop("GOOGLE_API_KEY", None)
        self._orig_jobright = os.environ.pop("JOBRIGHT_COOKIE_STRING", None)

    def tearDown(self):
        self._env_patch.stop()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)
        for var, val in (
            ("GEMINI_API_KEY", self._orig_gemini),
            ("GOOGLE_API_KEY", self._orig_google),
            ("JOBRIGHT_COOKIE_STRING", self._orig_jobright),
        ):
            if val is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = val

    def test_dry_run_prompts_nothing(self):
        with patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            result = bootstrap_profile.collect_secrets(dry_run=True)
            mock_confirm.assert_not_called()
        self.assertEqual(
            result, {"gemini_key_set": False, "jobright_cookie_set": False}
        )

    def test_entering_a_key_now_writes_it_to_this_profiles_own_env_file(self):
        with (
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
            patch("bootstrap_profile.questionary.password") as mock_password,
        ):
            mock_confirm.return_value.ask.side_effect = [
                True,
                False,
            ]  # yes to Gemini, no to JobRight
            mock_password.return_value.ask.return_value = "test-gemini-key-123"

            result = bootstrap_profile.collect_secrets(dry_run=False)

        self.assertTrue(result["gemini_key_set"])
        self.assertFalse(result["jobright_cookie_set"])
        with open(self.env_path) as f:
            content = f.read()
        self.assertIn("GEMINI_API_KEY", content)
        self.assertIn("test-gemini-key-123", content)

    def test_skips_the_prompt_entirely_when_already_configured_in_this_profiles_own_env(
        self,
    ):
        with open(self.env_path, "w", encoding="utf-8") as f:
            f.write(
                "GEMINI_API_KEY=already-in-this-profiles-env\nJOBRIGHT_COOKIE_STRING=already-in-this-profiles-env\n"
            )
        with (
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
            patch("bootstrap_profile.questionary.password") as mock_password,
        ):
            result = bootstrap_profile.collect_secrets(dry_run=False)
            mock_confirm.assert_not_called()
            mock_password.assert_not_called()
        self.assertEqual(result, {"gemini_key_set": True, "jobright_cookie_set": True})

    def test_accepting_the_shell_value_writes_it_to_this_profiles_own_env_instead_of_skipping(
        self,
    ):
        # A var being exported in the shell used to make collect_secrets()
        # skip writing anything to this profile's own .env at all --
        # defeating "two people sharing this checkout never share
        # credentials" the moment a second profile is bootstrapped on a
        # machine that already has GEMINI_API_KEY exported (B41). It
        # should now prompt, offering the shell value as a default.
        os.environ["GEMINI_API_KEY"] = "already-set-in-shell"
        os.environ["JOBRIGHT_COOKIE_STRING"] = "already-set-cookie"
        with (
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
            patch("bootstrap_profile.questionary.password") as mock_password,
        ):
            # 1) "Use the shell Gemini key for this profile too?" -> yes
            # 2) "Optional: set up JobRight scanning now?" -> yes
            # 3) "Use the shell JobRight cookie for this profile too?" -> yes
            mock_confirm.return_value.ask.side_effect = [True, True, True]

            result = bootstrap_profile.collect_secrets(dry_run=False)
            mock_password.assert_not_called()

        self.assertEqual(result, {"gemini_key_set": True, "jobright_cookie_set": True})
        with open(self.env_path) as f:
            content = f.read()
        self.assertIn("already-set-in-shell", content)
        self.assertIn("already-set-cookie", content)

    def test_declining_the_shell_value_falls_through_to_manual_entry(self):
        os.environ["GEMINI_API_KEY"] = "already-set-in-shell"
        with (
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
            patch("bootstrap_profile.questionary.password") as mock_password,
        ):
            # 1) "Use the shell Gemini key for this profile too?" -> no
            # 2) "Enter your Gemini API key now?" -> yes
            # 3) "Optional: set up JobRight scanning now?" -> no
            mock_confirm.return_value.ask.side_effect = [False, True, False]
            mock_password.return_value.ask.return_value = "manually-entered-key"

            result = bootstrap_profile.collect_secrets(dry_run=False)

        self.assertTrue(result["gemini_key_set"])
        with open(self.env_path) as f:
            content = f.read()
        self.assertIn("manually-entered-key", content)
        self.assertNotIn("already-set-in-shell", content)


class TestCollectLinkedinSearchQueries(unittest.TestCase):
    """
    Regression tests: linkedin_search_queries: didn't exist in the
    wizard-generated profile.yml template at all before this pass -- a new
    profile would silently fall back to target_roles.primary forever, with
    no way to set a real boolean query without hand-editing profile.yml
    afterward and knowing that field existed.
    """

    def test_dry_run_returns_empty_without_prompting(self):
        with patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            result = bootstrap_profile.collect_linkedin_search_queries(
                ["Marketing Manager"], dry_run=True
            )
            mock_confirm.assert_not_called()
        self.assertEqual(result, [])

    def test_declining_custom_terms_returns_empty_list(self):
        with patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = False
            result = bootstrap_profile.collect_linkedin_search_queries(
                ["Marketing Manager"]
            )
        self.assertEqual(result, [])

    def test_entering_custom_terms_collects_them_until_a_blank_line(self):
        with (
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
            patch("bootstrap_profile.questionary.text") as mock_text,
            patch("bootstrap_profile.questionary.checkbox") as mock_checkbox,
        ):
            # wants_custom=True, then decline the per-query workplace/location
            # override offer for each of the two entered terms.
            mock_confirm.return_value.ask.side_effect = [True, False, False]
            mock_text.return_value.ask.side_effect = [
                "Email OR Campaign",
                "Lifecycle",
                "",
            ]
            # Seniority-level checkbox at the end -- return the default
            # selection so nothing gets written to scan_filters.yml.
            mock_checkbox.return_value.ask.return_value = list(
                bootstrap_profile.content_settings.DEFAULT_LINKEDIN_EXPERIENCE_LEVELS
            )
            result = bootstrap_profile.collect_linkedin_search_queries(
                ["Marketing Manager"]
            )
        self.assertEqual(result, ["Email OR Campaign", "Lifecycle"])

    def test_per_query_override_produces_dict_entry(self):
        with (
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
            patch("bootstrap_profile.questionary.text") as mock_text,
            patch("bootstrap_profile.questionary.checkbox") as mock_checkbox,
        ):
            # wants_custom=True, then accept the override offer for the one
            # entered term.
            mock_confirm.return_value.ask.side_effect = [True, True]
            mock_text.return_value.ask.side_effect = [
                "Product Marketing",
                "Austin, TX",
                "",
            ]
            mock_checkbox.return_value.ask.side_effect = [
                ["onsite", "hybrid"],
                list(
                    bootstrap_profile.content_settings.DEFAULT_LINKEDIN_EXPERIENCE_LEVELS
                ),
            ]
            result = bootstrap_profile.collect_linkedin_search_queries(
                ["Marketing Manager"]
            )
        self.assertEqual(
            result,
            [
                {
                    "query": "Product Marketing",
                    "workplace_mode": ["onsite", "hybrid"],
                    "location": "Austin, TX",
                }
            ],
        )

    def test_non_default_seniority_selection_is_saved(self):
        with (
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
            patch("bootstrap_profile.questionary.text") as mock_text,
            patch("bootstrap_profile.questionary.checkbox") as mock_checkbox,
            patch("bootstrap_profile.content_settings.write_settings") as mock_write,
            patch("bootstrap_profile.content_settings.read_settings", return_value={}),
        ):
            mock_confirm.return_value.ask.side_effect = [True, False]
            mock_text.return_value.ask.side_effect = ["Lifecycle", ""]
            mock_checkbox.return_value.ask.return_value = ["director", "executive"]
            bootstrap_profile.collect_linkedin_search_queries(["Marketing Manager"])
        mock_write.assert_called_once_with(
            {"linkedin_experience_levels": ["director", "executive"]}
        )


class TestCollectSituationalRoles(BootstrapProfileTestCase):
    """
    Regression tests: situational_roles.yaml was scaffolded empty by
    bootstrap_bullet_bank.create_new_profile() and never surfaced during
    onboarding at all, so a new profile with real niche/optional past
    roles (e.g. animal-welfare work for animal-welfare postings) got no
    chance to configure them without already knowing the feature existed
    and hand-editing the YAML.
    """

    def test_dry_run_returns_empty_without_prompting(self):
        with patch("bootstrap_profile.questionary.checkbox") as mock_checkbox:
            result = bootstrap_profile.collect_situational_roles(dry_run=True)
            mock_checkbox.assert_not_called()
        self.assertEqual(result, [])

    def test_no_employers_yet_returns_empty_without_prompting(self):
        with patch("bootstrap_profile.questionary.checkbox") as mock_checkbox:
            result = bootstrap_profile.collect_situational_roles()
            mock_checkbox.assert_not_called()
        self.assertEqual(result, [])

    def test_selecting_none_returns_empty_list(self):
        self._write_timeline(
            [{"company": "Humane Society", "title": "Volunteer Coordinator"}]
        )
        with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", encoding="utf-8") as f:
            f.write("Role / Company,Bullet Point\nHumane Society,Did a thing\n")

        with patch("bootstrap_profile.questionary.checkbox") as mock_checkbox:
            mock_checkbox.return_value.ask.return_value = []
            result = bootstrap_profile.collect_situational_roles()
        self.assertEqual(result, [])

    def test_selected_company_with_keywords_becomes_a_role(self):
        self._write_timeline(
            [{"company": "Humane Society", "title": "Volunteer Coordinator"}]
        )
        with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", encoding="utf-8") as f:
            f.write("Role / Company,Bullet Point\nHumane Society,Did a thing\n")

        with (
            patch("bootstrap_profile.questionary.checkbox") as mock_checkbox,
            patch("bootstrap_profile.questionary.text") as mock_text,
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
        ):
            mock_checkbox.return_value.ask.return_value = ["Humane Society"]
            mock_text.return_value.ask.side_effect = [
                "Humane Society of Greater KC",  # display name
                "animal welfare, animal shelter",  # keywords
            ]
            mock_confirm.return_value.ask.return_value = True
            result = bootstrap_profile.collect_situational_roles()

        self.assertEqual(
            result,
            [
                {
                    "display_name": "Humane Society of Greater KC",
                    "bank_tag": "Humane Society",
                    "trigger_keywords": ["animal welfare", "animal shelter"],
                }
            ],
        )

    def test_redo_a_role_reprompts_with_previous_answers_as_defaults(self):
        self._write_timeline(
            [{"company": "Humane Society", "title": "Volunteer Coordinator"}]
        )
        with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", encoding="utf-8") as f:
            f.write("Role / Company,Bullet Point\nHumane Society,Did a thing\n")

        with (
            patch("bootstrap_profile.questionary.checkbox") as mock_checkbox,
            patch("bootstrap_profile.questionary.text") as mock_text,
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
        ):
            mock_checkbox.return_value.ask.return_value = ["Humane Society"]
            mock_text.return_value.ask.side_effect = [
                "Typo'd Name",  # display name, first pass
                "animal welfare",  # keywords, first pass
                "Humane Society of Greater KC",  # display name, redo
                "animal welfare, animal shelter",  # keywords, redo
            ]
            # First "Look right?" is declined (redo), second is accepted.
            mock_confirm.return_value.ask.side_effect = [False, True]
            result = bootstrap_profile.collect_situational_roles()

        self.assertEqual(
            result,
            [
                {
                    "display_name": "Humane Society of Greater KC",
                    "bank_tag": "Humane Society",
                    "trigger_keywords": ["animal welfare", "animal shelter"],
                }
            ],
        )

    def test_selected_company_with_no_keywords_is_dropped(self):
        self._write_timeline(
            [{"company": "Humane Society", "title": "Volunteer Coordinator"}]
        )
        with open(bootstrap_bullet_bank.DRAFT_CSV_PATH, "w", encoding="utf-8") as f:
            f.write("Role / Company,Bullet Point\nHumane Society,Did a thing\n")

        with (
            patch("bootstrap_profile.questionary.checkbox") as mock_checkbox,
            patch("bootstrap_profile.questionary.text") as mock_text,
            patch("bootstrap_profile.questionary.confirm") as mock_confirm,
        ):
            mock_checkbox.return_value.ask.return_value = ["Humane Society"]
            mock_text.return_value.ask.side_effect = ["Humane Society", ""]
            mock_confirm.return_value.ask.return_value = True
            result = bootstrap_profile.collect_situational_roles()

        self.assertEqual(result, [])


class TestWriteSituationalRoles(BootstrapProfileTestCase):

    def test_dry_run_writes_nothing(self):
        bootstrap_profile.write_situational_roles(
            [{"display_name": "X", "bank_tag": "X", "trigger_keywords": ["x"]}],
            dry_run=True,
        )
        self.assertFalse(os.path.exists(bootstrap_profile.SITUATIONAL_ROLES_PATH))

    def test_empty_roles_writes_valid_empty_scaffold(self):
        bootstrap_profile.write_situational_roles([])
        with open(bootstrap_profile.SITUATIONAL_ROLES_PATH, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        self.assertEqual(data["roles"], [])
        self.assertEqual(data["situational_min_bullets"], 2)

    def test_writes_roles_readable_by_situational_roles_module(self):
        roles = [
            {
                "display_name": "Humane Society of Greater KC",
                "bank_tag": "Humane Society",
                "trigger_keywords": ["animal welfare", "animal shelter"],
            }
        ]
        bootstrap_profile.write_situational_roles(roles)

        with patch(
            "profile_paths.situational_roles_path",
            return_value=bootstrap_profile.SITUATIONAL_ROLES_PATH,
        ):
            loaded = situational_roles.load_situational_roles()
        self.assertIn("Humane Society of Greater KC", loaded["roles"])
        entry = loaded["roles"]["Humane Society of Greater KC"]
        self.assertEqual(entry["bank_tag"], "Humane Society")
        self.assertEqual(
            entry["trigger_keywords"], ["animal welfare", "animal shelter"]
        )

    def test_no_confirm_prompt_when_no_existing_file(self):
        with patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            bootstrap_profile.write_situational_roles(
                [{"display_name": "X", "bank_tag": "X", "trigger_keywords": ["x"]}]
            )
            mock_confirm.assert_not_called()

    def test_declining_overwrite_leaves_existing_roles_untouched(self):
        bootstrap_profile.write_situational_roles(
            [
                {
                    "display_name": "Original",
                    "bank_tag": "Original",
                    "trigger_keywords": ["orig"],
                }
            ]
        )
        with patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = False
            bootstrap_profile.write_situational_roles(
                [
                    {
                        "display_name": "New",
                        "bank_tag": "New",
                        "trigger_keywords": ["new"],
                    }
                ]
            )
        with open(bootstrap_profile.SITUATIONAL_ROLES_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Original", content)
        self.assertNotIn("New", content)

    def test_accepting_overwrite_replaces_existing_roles(self):
        bootstrap_profile.write_situational_roles(
            [
                {
                    "display_name": "Original",
                    "bank_tag": "Original",
                    "trigger_keywords": ["orig"],
                }
            ]
        )
        with patch("bootstrap_profile.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = True
            bootstrap_profile.write_situational_roles(
                [
                    {
                        "display_name": "New",
                        "bank_tag": "New",
                        "trigger_keywords": ["new"],
                    }
                ]
            )
        with open(bootstrap_profile.SITUATIONAL_ROLES_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertIn("New", content)
        self.assertNotIn("Original", content)


class TestWriteBackgroundGuide(BootstrapProfileTestCase):

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.bootstrap_extractors.draft_background_guide")
    def test_accepts_draft_and_writes_file(self, mock_draft, mock_select):
        self._touch_source("resume.txt")
        self._write_checkpoint(
            {
                "resume.txt": {
                    "status": "done",
                    "doc_type": "resume",
                    "work_experience": [
                        {
                            "company": "Acme Corp",
                            "title": "Marketer",
                            "start_date": "2020",
                            "end_date": "2022",
                            "achievements": ["Grew email list by 40%"],
                        }
                    ],
                }
            }
        )
        mock_draft.return_value = "A marketer who blends writing and systems thinking."
        mock_select.return_value.ask.return_value = "accept"

        bootstrap_profile.write_background_guide(bootstrap_profile._load_checkpoint())

        with open(bootstrap_profile.BACKGROUND_GUIDE_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "A marketer who blends writing and systems thinking.")

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.bootstrap_extractors.draft_background_guide")
    def test_skip_writes_empty_file(self, mock_draft, mock_select):
        self._touch_source("resume.txt")
        self._write_checkpoint({"resume.txt": {"status": "done", "doc_type": "resume"}})
        mock_draft.return_value = "Some draft text."
        mock_select.return_value.ask.return_value = "skip"

        bootstrap_profile.write_background_guide(bootstrap_profile._load_checkpoint())

        with open(bootstrap_profile.BACKGROUND_GUIDE_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "")

    def test_dry_run_writes_without_prompting(self):
        with (
            patch("bootstrap_profile.questionary.select") as mock_select,
            patch(
                "bootstrap_profile.bootstrap_extractors.draft_background_guide",
                return_value="",
            ) as mock_draft,
        ):
            bootstrap_profile.write_background_guide({}, dry_run=True)
            mock_select.assert_not_called()
            mock_draft.assert_called_once()

    def test_pdf_sourced_document_still_contributes_source_text(self):
        # Regression test: a PDF (or image) document never has local text
        # to re-read -- _resolve_text_or_upload() returns text=None for
        # those, upload_path instead -- so no source .txt file is written
        # here at all, only a checkpoint entry shaped the way real
        # ingestion of an uploaded PDF resume actually produces one
        # (work_experience from the Files-API extraction, no source file
        # on disk). Gathering source texts used to re-open the original
        # path and got nothing back for exactly this case, which is why an
        # all-PDF document set produced an empty background guide.
        checkpoint = {
            "resume.pdf": {
                "status": "done",
                "doc_type": "resume",
                "work_experience": [
                    {
                        "company": "Acme Corp",
                        "title": "Marketer",
                        "start_date": "2020",
                        "end_date": "2022",
                        "achievements": ["Grew email list by 40%"],
                    }
                ],
            }
        }

        texts = bootstrap_profile._gather_background_source_texts(checkpoint)

        self.assertEqual(len(texts), 1)
        self.assertIn("Acme Corp", texts[0])
        self.assertIn("Grew email list by 40%", texts[0])


class TestWriteVoiceAnchors(BootstrapProfileTestCase):

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.bootstrap_extractors.draft_voice_anchors")
    def test_accepts_draft_and_writes_file(self, mock_draft, mock_select):
        self._touch_source("cover_letter.txt")
        self._write_checkpoint(
            {
                "cover_letter.txt": {
                    "status": "done",
                    "doc_type": "other",
                    "achievements": [
                        {"raw_text": "A real first-person writing sample."}
                    ],
                }
            }
        )
        mock_draft.return_value = "### Why this role\n\nSomething genuine.\n"
        mock_select.return_value.ask.return_value = "accept"

        bootstrap_profile.write_voice_anchors(bootstrap_profile._load_checkpoint())

        with open(bootstrap_profile.VOICE_ANCHORS_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "### Why this role\n\nSomething genuine.\n")

    @patch("bootstrap_profile.questionary.select")
    @patch("bootstrap_profile.bootstrap_extractors.draft_voice_anchors")
    def test_skip_writes_empty_file(self, mock_draft, mock_select):
        self._touch_source("cover_letter.txt")
        self._write_checkpoint(
            {"cover_letter.txt": {"status": "done", "doc_type": "other"}}
        )
        mock_draft.return_value = "Some draft text."
        mock_select.return_value.ask.return_value = "skip"

        bootstrap_profile.write_voice_anchors(bootstrap_profile._load_checkpoint())

        with open(bootstrap_profile.VOICE_ANCHORS_PATH, encoding="utf-8") as f:
            content = f.read()
        self.assertEqual(content, "")

    def test_dry_run_writes_without_prompting(self):
        with (
            patch("bootstrap_profile.questionary.select") as mock_select,
            patch(
                "bootstrap_profile.bootstrap_extractors.draft_voice_anchors",
                return_value="",
            ) as mock_draft,
        ):
            bootstrap_profile.write_voice_anchors({}, dry_run=True)
            mock_select.assert_not_called()
            mock_draft.assert_called_once()

    def test_gathers_other_doc_type_unlike_background_guide(self):
        # Regression test: a genuine writing sample (cover letter, essay)
        # has no dedicated doc_type and usually classifies as "other" --
        # _gather_background_source_texts() deliberately excludes "other",
        # but voice anchors need exactly this kind of first-person text.
        checkpoint = {
            "essay.txt": {
                "status": "done",
                "doc_type": "other",
                "achievements": [{"raw_text": "A real first-person writing sample."}],
            }
        }

        texts = bootstrap_profile._gather_voice_anchor_source_texts(checkpoint)

        self.assertEqual(texts, ["A real first-person writing sample."])


class TestRunProfileSetup(BootstrapProfileTestCase):

    @patch("bootstrap_profile.report_job_board_readiness")
    @patch("bootstrap_profile.offer_settings_screens")
    @patch("bootstrap_profile.collect_deal_breakers", return_value=[])
    @patch("bootstrap_profile.collect_voice_calibration_example", return_value="")
    @patch("bootstrap_profile.write_voice_anchors")
    @patch("bootstrap_profile.write_background_guide")
    @patch("bootstrap_profile.write_cv_md")
    @patch("bootstrap_profile.write_verified_ledger")
    @patch("bootstrap_profile.stage_candidate_facts", return_value=0)
    @patch("bootstrap_profile.seed_scan_filters_from_target_roles")
    @patch("bootstrap_profile.write_portals_yml")
    @patch("bootstrap_profile.write_profile_yml")
    @patch("bootstrap_profile.bootstrap_extractors.generate_tag_taxonomy")
    @patch("bootstrap_profile.collect_linkedin_search_queries", return_value=[])
    @patch("bootstrap_profile.collect_identity")
    @patch("bootstrap_profile._guess_recommendations", return_value=[])
    def test_calls_every_writer_in_order(
        self,
        mock_guess_recs,
        mock_collect_identity,
        mock_collect_linkedin,
        mock_generate_tags,
        mock_write_profile,
        mock_write_portals,
        mock_seed_scan_filters,
        mock_stage_facts,
        mock_write_ledger,
        mock_write_cv,
        mock_write_bg,
        mock_write_voice,
        mock_collect_voice_calibration,
        mock_collect_deal_breakers,
        mock_offer_settings,
        mock_job_board_readiness,
    ):
        mock_collect_identity.return_value = {
            "full_name": "Jamie Rivera",
            "primary_roles": ["Marketing Manager"],
            "secondary_roles": [],
        }
        mock_generate_tags.return_value = bootstrap_extractors.TagTaxonomy()

        summary = bootstrap_profile.run_profile_setup()

        mock_collect_linkedin.assert_called_once()
        mock_generate_tags.assert_called_once()
        mock_write_profile.assert_called_once()
        mock_write_portals.assert_called_once()
        mock_seed_scan_filters.assert_called_once()
        mock_write_ledger.assert_called_once()
        mock_stage_facts.assert_called_once()
        mock_write_cv.assert_called_once()
        mock_write_bg.assert_called_once()
        mock_write_voice.assert_called_once()
        self.assertEqual(summary["full_name"], "Jamie Rivera")
        self.assertEqual(summary["primary_roles"], 1)
        self.assertEqual(summary["tags_generated"], 0)
        self.assertEqual(summary["linkedin_search_queries"], 0)


class TestVerifiedLedgerDataLoss(unittest.TestCase):
    """write_verified_ledger() overwrites all three ledger files
    unconditionally. Two separate defects made that destructive:
    the bullet source was a bootstrap-only CSV that no established
    profile has, and an empty extraction was still written out."""

    def _make_kb(self, tmpdir):
        paths = {
            "metrics": os.path.join(tmpdir, "verified_metrics.json"),
            "tools": os.path.join(tmpdir, "verified_tools.json"),
            "projects": os.path.join(tmpdir, "verified_projects.json"),
            "facts": os.path.join(tmpdir, "verified_facts.json"),
        }
        for key, path in paths.items():
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"_meta": {"total_entries": 2}, key: ["real", "data"]}, f)
        return paths

    def test_empty_extraction_does_not_erase_existing_ledger_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._make_kb(tmpdir)
            before = {k: open(v, encoding="utf-8").read() for k, v in paths.items()}

            with (
                patch.object(
                    bootstrap_profile, "VERIFIED_METRICS_PATH", paths["metrics"]
                ),
                patch.object(bootstrap_profile, "VERIFIED_TOOLS_PATH", paths["tools"]),
                patch.object(
                    bootstrap_profile, "VERIFIED_PROJECTS_PATH", paths["projects"]
                ),
                patch.object(bootstrap_profile, "VERIFIED_FACTS_PATH", paths["facts"]),
                patch.object(
                    bootstrap_profile,
                    "_achievements_summary_text_by_employer",
                    return_value="",
                ),
            ):
                bootstrap_profile.write_verified_ledger()

            after = {k: open(v, encoding="utf-8").read() for k, v in paths.items()}
            self.assertEqual(before, after, "an empty extraction erased real KB data")

    def test_existing_seed_files_are_never_blanked(self):
        """Everything below the metrics/tools/projects block seeds a NEW
        profile. Those writes were unconditional, so running this on an
        established profile blanked a 97 KB verified-claims.csv and a
        curated facts ledger with no prompt and no error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self._make_kb(tmpdir)
            seeds = {
                "VERIFIED_FACTS_PATH": os.path.join(tmpdir, "verified_facts.json"),
                "VERIFIED_CLAIMS_PATH": os.path.join(tmpdir, "verified-claims.csv"),
                "EVIDENCE_GRAPH_PATH": os.path.join(tmpdir, "evidence_graph.json"),
                "EVIDENCE_GUIDE_PATH": os.path.join(tmpdir, "evidence-guide.csv"),
                "SCREENSHOT_METRICS_PATH": os.path.join(tmpdir, "shots.csv"),
                "RECRUITER_PATTERNS_PATH": os.path.join(tmpdir, "patterns.json"),
            }
            for path in seeds.values():
                with open(path, "w", encoding="utf-8") as f:
                    f.write("REAL CURATED CONTENT")

            extraction = bootstrap_extractors.LedgerExtraction(
                metrics=[],
                tools=[
                    bootstrap_extractors.NamedLedgerItem(name="Braze", employer="Acme")
                ],
                projects=[],
            )

            patches = [
                patch.object(
                    bootstrap_profile, "VERIFIED_METRICS_PATH", paths["metrics"]
                ),
                patch.object(bootstrap_profile, "VERIFIED_TOOLS_PATH", paths["tools"]),
                patch.object(
                    bootstrap_profile, "VERIFIED_PROJECTS_PATH", paths["projects"]
                ),
                patch.object(
                    bootstrap_profile,
                    "_achievements_summary_text_by_employer",
                    return_value="[Acme] - used Braze",
                ),
                patch.object(
                    bootstrap_extractors,
                    "extract_ledger_entries_chunked",
                    return_value=extraction,
                ),
            ]
            for name, path in seeds.items():
                patches.append(patch.object(bootstrap_profile, name, path))

            for p in patches:
                p.start()
            try:
                bootstrap_profile.write_verified_ledger()
            finally:
                for p in patches:
                    p.stop()

            for name, path in seeds.items():
                with open(path, encoding="utf-8") as f:
                    self.assertEqual(
                        f.read(), "REAL CURATED CONTENT", f"{name} was blanked"
                    )

    def test_seed_is_written_when_the_file_is_absent(self):
        """The guard must not break a genuine first-time bootstrap."""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = os.path.join(tmpdir, "verified_facts.json")
            self.assertTrue(bootstrap_profile._seed_only_if_absent(missing))

            with open(missing, "w", encoding="utf-8") as f:
                f.write("x")
            self.assertFalse(bootstrap_profile._seed_only_if_absent(missing))

    def test_zero_byte_seed_counts_as_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty = os.path.join(tmpdir, "empty.json")
            open(empty, "w").close()
            self.assertTrue(bootstrap_profile._seed_only_if_absent(empty))

    def test_bullet_source_falls_back_to_the_established_bullet_bank(self):
        """An established profile has no bullet-bank-draft.csv -- reading
        only that path is what produced the empty extraction above."""
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = os.path.join(tmpdir, "bullet-bank-draft.csv")
            clean = os.path.join(tmpdir, "bullet-bank-clean.csv")
            with open(clean, "w", encoding="utf-8") as f:
                f.write("Role / Company,Tags,Bullet Point\nAcme,[x],- Did a thing\n")

            with (
                patch.object(bootstrap_bullet_bank, "DRAFT_CSV_PATH", draft),
                patch.object(bootstrap_bullet_bank, "BULLET_BANK_CLEAN_PATH", clean),
            ):
                self.assertEqual(bootstrap_profile._bullet_source_path(), clean)

                text = bootstrap_profile._achievements_summary_text_by_employer()
                self.assertIn("[Acme] - Did a thing", text)

    def test_draft_csv_still_wins_while_a_profile_is_being_bootstrapped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            draft = os.path.join(tmpdir, "bullet-bank-draft.csv")
            clean = os.path.join(tmpdir, "bullet-bank-clean.csv")
            for path, company in ((draft, "DraftCo"), (clean, "CleanCo")):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(f"Role / Company,Tags,Bullet Point\n{company},[x],- b\n")

            with (
                patch.object(bootstrap_bullet_bank, "DRAFT_CSV_PATH", draft),
                patch.object(bootstrap_bullet_bank, "BULLET_BANK_CLEAN_PATH", clean),
            ):
                self.assertEqual(bootstrap_profile._bullet_source_path(), draft)

    def test_no_bullet_source_at_all_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.object(
                    bootstrap_bullet_bank,
                    "DRAFT_CSV_PATH",
                    os.path.join(tmpdir, "nope.csv"),
                ),
                patch.object(
                    bootstrap_bullet_bank,
                    "BULLET_BANK_CLEAN_PATH",
                    os.path.join(tmpdir, "also-nope.csv"),
                ),
            ):
                self.assertIsNone(bootstrap_profile._bullet_source_path())
                self.assertEqual(
                    bootstrap_profile._achievements_summary_text_by_employer(), ""
                )


class TestPersonalNarrativeFields(BootstrapProfileTestCase):
    """Deliberately-manual profile.yml fields (narrative, superpowers,
    background_context, deal_breakers, industries_of_genuine_fit) -- get/
    set pairs used by the Settings & Upkeep editor and the blank-field
    banner reminder. Never auto-generated (see bootstrap_profile.py's own
    comment on this), so what matters here is that editing one preserves
    every surrounding hand-written comment, the same reasoning already
    covered for voice_calibration_example."""

    # _PROFILE_YML_TEMPLATE is an unfilled format-string (real values only
    # land via write_profile_yml()'s .format() call) -- a minimal, valid,
    # hand-written fixture is simpler and more targeted here than driving
    # that whole machinery just to get a parseable file.
    _FIXTURE = """# Career-Ops Profile Configuration
# Generated by bootstrap -- review and expand the sections below any time.

candidate:
  full_name: "Test Candidate"

narrative:
  # A 1-2 sentence headline summarizing your professional identity.
  headline: ""

  # Optional: why you're job-searching now / your story if there's a
  # gap or transition. Leave blank if not applicable.
  exit_story: ""

superpowers:
  # 3-5 things you're uniquely good at, each with a real example. These
  # often come from your own self-reflection or feedback you've received.
  - ""

# A paragraph on how your background came together -- the different
# tracks/experiences that combine into what you do now.
background_context: ""

industries_of_genuine_fit:
  # Industries or company types where you'd genuinely want to work.
  - ""

deal_breakers:
  # Things that would make a role a bad fit, with the specific reason.
  - ""

proof_points: []
  # Your single best, most specific hero metric per major achievement.
"""

    def setUp(self):
        super().setUp()
        with open(bootstrap_profile.PROFILE_YML_PATH, "w", encoding="utf-8") as f:
            f.write(self._FIXTURE)

    def test_all_fields_blank_on_fresh_scaffold(self):
        self.assertEqual(
            bootstrap_profile.blank_personal_narrative_fields(),
            [label for label, *_ in bootstrap_profile.PERSONAL_NARRATIVE_FIELDS],
        )

    def test_scalar_fields_round_trip_and_drop_from_blank_list(self):
        bootstrap_profile.set_narrative_headline("Bridges IoT sensors and ML.")
        bootstrap_profile.set_narrative_exit_story("Seeking new opportunities.")
        bootstrap_profile.set_background_context("How it all came together.")

        self.assertEqual(
            bootstrap_profile.get_narrative_headline(), "Bridges IoT sensors and ML."
        )
        self.assertEqual(
            bootstrap_profile.get_narrative_exit_story(), "Seeking new opportunities."
        )
        self.assertEqual(
            bootstrap_profile.get_background_context(), "How it all came together."
        )
        blank = bootstrap_profile.blank_personal_narrative_fields()
        self.assertNotIn("Headline", blank)
        self.assertNotIn("Exit story", blank)
        self.assertNotIn("Background context", blank)

    def test_list_fields_round_trip(self):
        bootstrap_profile.set_superpowers(["Time-series anomaly detection", "IoT"])
        bootstrap_profile.set_deal_breakers(["No fully on-site roles"])
        bootstrap_profile.set_industries_of_genuine_fit(["Robotics", "Climate tech"])

        self.assertEqual(
            bootstrap_profile.get_superpowers(),
            ["Time-series anomaly detection", "IoT"],
        )
        self.assertEqual(
            bootstrap_profile.get_deal_breakers(), ["No fully on-site roles"]
        )
        self.assertEqual(
            bootstrap_profile.get_industries_of_genuine_fit(),
            ["Robotics", "Climate tech"],
        )

    def test_editing_one_field_preserves_unrelated_comments(self):
        bootstrap_profile.set_narrative_headline("A real headline.")
        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            content = f.read()
        # Comments belonging to OTHER fields must survive untouched.
        self.assertIn("# Industries or company types", content)
        self.assertIn("# Your single best, most specific hero metric", content)
        self.assertIn(
            "# 3-5 things you're uniquely good at, each with a real example.",
            content,
        )
        # The whole file must still parse as valid YAML.
        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            parsed = yaml.safe_load(f)
        self.assertEqual(parsed["narrative"]["headline"], "A real headline.")

    def test_setting_empty_list_writes_single_blank_placeholder(self):
        bootstrap_profile.set_superpowers([])
        # Matches the bootstrap scaffold's own convention for "unfilled."
        self.assertEqual(bootstrap_profile.get_superpowers(), [])
        with open(bootstrap_profile.PROFILE_YML_PATH, encoding="utf-8") as f:
            parsed = yaml.safe_load(f)
        self.assertEqual(parsed["superpowers"], [""])


if __name__ == "__main__":
    unittest.main()
