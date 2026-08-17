import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
sys.path.insert(0, SCRIPTS_DIR)

import jd_manager  # noqa: E402
import orchestrator  # noqa: E402
import profile_paths  # noqa: E402


class TestCoverLetterSchemaNewFields(unittest.TestCase):

    def test_contact_fields_default_to_empty_string(self):
        model = orchestrator.CoverLetterSchema(
            company_name="Acme", greeting="Dear Acme Corp Hiring Team,",
            body_paragraphs=["p1", "p2"], sign_off="Sincerely,",
        )
        self.assertEqual(model.contact_name, "")
        self.assertEqual(model.contact_title, "")


class TestResolveCompanyLocation(unittest.TestCase):

    def test_prefers_research_hq_location(self):
        result = orchestrator._resolve_company_location(
            {"company_hq_location": "Austin, TX"}, {"location": "Remote"})
        self.assertEqual(result, "Austin, TX")

    def test_falls_back_to_jd_location_when_research_has_none(self):
        result = orchestrator._resolve_company_location({"company_hq_location": ""}, {"location": "Remote"})
        self.assertEqual(result, "Remote")

    def test_falls_back_to_jd_location_when_research_is_none(self):
        result = orchestrator._resolve_company_location(None, {"location": "Buffalo, NY"})
        self.assertEqual(result, "Buffalo, NY")

    def test_returns_empty_string_when_nothing_known(self):
        self.assertEqual(orchestrator._resolve_company_location(None, {}), "")

    def test_returns_jd_location_even_for_a_remote_role(self):
        # No filtering by remote/on-site -- shown whenever known.
        result = orchestrator._resolve_company_location(None, {"location": "Remote"})
        self.assertEqual(result, "Remote")


class TestReadMatchingResumeTagline(unittest.TestCase):

    def setUp(self):
        self.resume_dir = os.path.join(profile_paths.output_dir(), "json")
        os.makedirs(self.resume_dir, exist_ok=True)
        self.resume_path = os.path.join(self.resume_dir, "_tmp_enrichment_stem_Resume.json")

    def tearDown(self):
        if os.path.exists(self.resume_path):
            os.remove(self.resume_path)

    def test_returns_empty_string_when_no_matching_resume_exists(self):
        self.assertEqual(orchestrator._read_matching_resume_tagline("_tmp_enrichment_stem"), "")

    def test_returns_tagline_from_matching_resume_json(self):
        with open(self.resume_path, "w", encoding="utf-8") as f:
            json.dump({"TAGLINE": "CONTENT STRATEGIST | SEO"}, f)
        self.assertEqual(
            orchestrator._read_matching_resume_tagline("_tmp_enrichment_stem"),
            "CONTENT STRATEGIST | SEO",
        )

    def test_returns_empty_string_on_malformed_json(self):
        with open(self.resume_path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        self.assertEqual(orchestrator._read_matching_resume_tagline("_tmp_enrichment_stem"), "")


class TestCoverLetterEnrichmentWiring(unittest.TestCase):
    """Confirms build_tailored_coverletter() merges tagline, resolved
    company_location, and contact fallback into the saved letter_data."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_enrichment.json")
        self.jd_json = {
            "job_title": "Content Strategist",
            "company_name": "Acme Corp",
            "location": "Remote",
            "description": "We are hiring a Content Strategist.",
        }
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(self.jd_json, f)

        self.stem = orchestrator._build_output_stem(self.jd_path)
        self.resume_json_path = os.path.join(self.engine.output_json_dir, f"{self.stem}_Resume.json")
        os.makedirs(self.engine.output_json_dir, exist_ok=True)
        with open(self.resume_json_path, "w", encoding="utf-8") as f:
            json.dump({"TAGLINE": "CONTENT STRATEGIST | SEO | LIFECYCLE MARKETING"}, f)

        self.json_out = os.path.join(self.engine.output_json_dir, f"{self.stem}_CoverLetter.json")
        self.html_out = os.path.join(self.engine.output_html_dir, f"{self.stem}_CoverLetter.html")

    def tearDown(self):
        for path in (self.jd_path, self.resume_json_path, self.json_out, self.html_out):
            if os.path.exists(path):
                os.remove(path)

    def _clean_letter_json(self):
        return json.dumps({
            "company_name": "Acme Corp",
            "greeting": "Dear Acme Corp Hiring Team,",
            "contact_name": "",
            "contact_title": "",
            "body_paragraphs": [
                "I'm excited to apply for this role at Acme Corp.",
                "My background lines up well with what you need.",
            ],
            "sign_off": "Sincerely,",
        })

    def _run_build(self):
        with patch("orchestrator.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("orchestrator.render_coverletter"), \
             patch("orchestrator.validate_pdf_text.validate_coverletter_pdf_text", return_value=[]):
            return self.engine.build_tailored_coverletter(self.jd_path)

    @patch.object(orchestrator.ResumeEngine, "research_company",
                   return_value={"company_hq_location": "Austin, TX", "company_facts": [], "notable_highlights": []})
    @patch("orchestrator.GeminiClient.generate")
    def test_tagline_and_research_location_land_in_saved_letter(self, mock_generate, mock_research):
        mock_generate.return_value = (self._clean_letter_json(), {})
        result = self._run_build()
        self.assertEqual(result["tagline"], "CONTENT STRATEGIST | SEO | LIFECYCLE MARKETING")
        self.assertEqual(result["company_location"], "Austin, TX")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_falls_back_to_jd_location_when_research_has_none(self, mock_generate, mock_research):
        mock_generate.return_value = (self._clean_letter_json(), {})
        result = self._run_build()
        self.assertEqual(result["company_location"], "Remote")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_contact_fallback_fills_from_scraped_jd_contacts(self, mock_generate, mock_research):
        self.jd_json["social_connections"] = [
            {"fullName": "Maggie Smith", "jobTitle": "HR Manager", "companyName": "Acme Corp"},
        ]
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(self.jd_json, f)
        mock_generate.return_value = (self._clean_letter_json(), {})
        result = self._run_build()
        self.assertEqual(result["contact_name"], "Maggie Smith")
        self.assertEqual(result["contact_title"], "HR Manager")


class TestReferralInjection(unittest.TestCase):
    """Feature #5: a saved _referral (jd_manager.save_referral()) should be
    folded into build_tailored_coverletter()'s system_instruction as a
    '=== REFERRAL ===' block; a JD with no referral saved should produce
    no such block at all."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_referral.json")
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump({
                "job_title": "Content Strategist",
                "company_name": "Acme Corp",
                "description": "We are hiring a Content Strategist.",
            }, f)

        self.stem = orchestrator._build_output_stem(self.jd_path)
        self.json_out = os.path.join(self.engine.output_json_dir, f"{self.stem}_CoverLetter.json")
        self.html_out = os.path.join(self.engine.output_html_dir, f"{self.stem}_CoverLetter.html")

    def tearDown(self):
        for path in (self.jd_path, self.json_out, self.html_out):
            if os.path.exists(path):
                os.remove(path)

    def _clean_letter_json(self):
        return json.dumps({
            "company_name": "Acme Corp",
            "greeting": "Dear Acme Corp Hiring Team,",
            "contact_name": "",
            "contact_title": "",
            "body_paragraphs": [
                "When Acme Corp scaling its Content Strategist function, Jane Doe suggested I reach out.",
                "My background lines up well with what you need.",
            ],
            "sign_off": "Sincerely,",
        })

    def _run_build(self):
        with patch("orchestrator.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("orchestrator.render_coverletter"), \
             patch("orchestrator.validate_pdf_text.validate_coverletter_pdf_text", return_value=[]):
            return self.engine.build_tailored_coverletter(self.jd_path)

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_referral_block_present_in_system_instruction_when_saved(self, mock_generate, mock_research):
        jd_manager.save_referral(self.jd_path, "Jane Doe, former coworker")
        mock_generate.return_value = (self._clean_letter_json(), {})
        self._run_build()
        # index -1, not 0: when this JD has no checkpoint jd_keywords (Group
        # B, Feature #12), build_tailored_coverletter() makes an earlier
        # GeminiClient.generate() call to extract them first, so the letter
        # generation call is the *last* call, not the first.
        system_instruction = mock_generate.call_args_list[-1].kwargs["system_instruction"]
        # The prompt template's own instructions always mention the
        # "=== REFERRAL ===" marker by name (explaining the convention), so
        # check for the actual injected content instead of the marker text.
        self.assertIn("Jane Doe, former coworker", system_instruction)
        self.assertIn("The candidate has a referral for this specific role", system_instruction)

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_no_referral_block_when_none_saved(self, mock_generate, mock_research):
        mock_generate.return_value = (self._clean_letter_json(), {})
        self._run_build()
        # index -1, not 0: when this JD has no checkpoint jd_keywords (Group
        # B, Feature #12), build_tailored_coverletter() makes an earlier
        # GeminiClient.generate() call to extract them first, so the letter
        # generation call is the *last* call, not the first.
        system_instruction = mock_generate.call_args_list[-1].kwargs["system_instruction"]
        self.assertNotIn("The candidate has a referral for this specific role", system_instruction)


class TestBuildKeywordBlock(unittest.TestCase):
    """Feature #12: unit coverage for the pure formatting helper, separate
    from the integration wiring below."""

    def test_returns_empty_string_when_no_keywords(self):
        self.assertEqual(orchestrator._build_keyword_block(None, None), "")
        self.assertEqual(orchestrator._build_keyword_block({}, None), "")

    def test_caps_at_eight_terms_across_all_three_fields(self):
        keywords = {
            "tools": ["A", "B", "C", "D", "E", "F"],
            "hard_skills": ["G", "H", "I"],
            "core_functions": ["J", "K"],
        }
        block = orchestrator._build_keyword_block(keywords, None)
        terms_line = next(line for line in block.splitlines() if line.startswith("Top terms"))
        kept = [t.strip() for t in terms_line.split(":", 1)[1].split(",")]
        self.assertEqual(kept, ["A", "B", "C", "D", "E", "F", "G", "H"])

    def test_unknown_tier_gets_light_touch_wording(self):
        block = orchestrator._build_keyword_block({"tools": ["Figma"]}, None)
        self.assertIn("helpful context", block)

    def test_enterprise_high_tier_gets_critical_wording(self):
        block = orchestrator._build_keyword_block(
            {"tools": ["Figma"]}, {"weight_tier": "enterprise_high"})
        self.assertIn("critical", block)


class TestAtsClassificationAndKeywordFrontLoading(unittest.TestCase):
    """Feature #1 (ATS classification) + #12 (keyword front-loading), Group
    B of docs/superpowers/plans/2026-08-17-cover-letter-blueprint-roadmap.md."""

    def setUp(self):
        self.engine = orchestrator.ResumeEngine()
        self.jd_path = os.path.join(os.path.dirname(__file__), "_tmp_jd_ats_classification.json")
        self.job_key = None
        self.stem = None

    def tearDown(self):
        for path in (self.jd_path, self.json_out_path(), self.html_out_path()):
            if path and os.path.exists(path):
                os.remove(path)
        if self.job_key:
            checkpoint_path = jd_manager._checkpoint_path(self.job_key)
            if os.path.exists(checkpoint_path):
                os.remove(checkpoint_path)

    def json_out_path(self):
        return os.path.join(self.engine.output_json_dir, f"{self.stem}_CoverLetter.json") if self.stem else None

    def html_out_path(self):
        return os.path.join(self.engine.output_html_dir, f"{self.stem}_CoverLetter.html") if self.stem else None

    def _write_jd(self, source_url=""):
        jd_json = {
            "job_title": "Content Strategist",
            "company_name": "Acme Corp",
            "description": "We are hiring a Content Strategist.",
        }
        if source_url:
            jd_json["source_url"] = source_url
        with open(self.jd_path, "w", encoding="utf-8") as f:
            json.dump(jd_json, f)
        self.stem = orchestrator._build_output_stem(self.jd_path)
        self.job_key = jd_manager.compute_job_key(self.jd_path)

    def _seed_checkpoint_keywords(self, keywords):
        # Recomputed fresh (not the job_key cached in _write_jd) since any
        # intervening save_ats_classification() call rewrites the JD file
        # and, absent a source_job_id, changes compute_job_key()'s content
        # hash -- see the comment on the caller that hits this.
        self.job_key = jd_manager.compute_job_key(self.jd_path)
        jd_manager.save_checkpoint(self.job_key, {"jd_keywords": keywords})

    def _clean_letter_json(self):
        # 300+ words across both paragraphs -- validate_coverletter.py
        # enforces a 300-450 word count (Group A, Feature #4), so a short
        # fixture triggers the one-shot retry and consumes an extra
        # GeminiClient.generate() call these tests don't account for.
        p1 = (
            "When Acme Corp scales its Content Strategist function, clear positioning becomes "
            "essential to the team's next chapter, and that is where my background fits well. "
            "Content work is often treated as a downstream deliverable, something produced after "
            "strategy is decided elsewhere, but the strongest programs treat it as strategy itself, "
            "with research and audience insight shaping the plan from the earliest stages rather than "
            "layered on top afterward. I have spent years building narrative frameworks that translate "
            "complex product ideas into messaging real audiences actually understand, testing which "
            "angles resonate before a campaign goes live, and refining that message continuously as "
            "markets and audiences shift underneath it. That habit of pairing structured research with "
            "sharp editorial judgment, rather than leaning on either alone, is what a growing content "
            "function needs most in its next hire, and it is the strength I would bring to this team "
            "from the very first week on the job."
        )
        p2 = (
            "Beyond the writing itself, what draws me to this particular role is the chance to help "
            "shape how a growing team talks about its own work, internally and externally, in a voice "
            "that feels consistent no matter who is holding the pen that day. Building that kind of "
            "consistency takes more than a style guide; it takes someone willing to sit with product, "
            "sales, and support teams long enough to understand what each audience actually needs to "
            "hear, then translate that understanding into content that serves all of them without "
            "diluting the message for any one group. I enjoy that kind of cross-functional problem "
            "solving, and I would welcome the opportunity to bring that same approach to Acme Corp, "
            "learning the specifics of this market quickly while applying lessons carried over from "
            "prior roles where the stakes and the audience looked different but the underlying "
            "discipline was the same."
        )
        return json.dumps({
            "company_name": "Acme Corp",
            "greeting": "Dear Acme Corp Hiring Team,",
            "contact_name": "",
            "contact_title": "",
            "body_paragraphs": [p1, p2],
            "sign_off": "Sincerely,",
        })

    def _run_build(self):
        with patch("orchestrator.subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")), \
             patch("orchestrator.render_coverletter"), \
             patch("orchestrator.validate_pdf_text.validate_coverletter_pdf_text", return_value=[]):
            return self.engine.build_tailored_coverletter(self.jd_path)

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_workday_source_url_classified_enterprise_high_and_persisted(self, mock_generate, mock_research):
        self._write_jd(source_url="https://acme.wd1.myworkdayjobs.com/External/job/123")
        self._seed_checkpoint_keywords({"tools": ["Salesforce"], "hard_skills": [], "core_functions": []})
        mock_generate.return_value = (self._clean_letter_json(), {})
        self._run_build()

        system_instruction = mock_generate.call_args_list[-1].kwargs["system_instruction"]
        self.assertIn("=== KEYWORDS ===", system_instruction)
        self.assertIn("Salesforce", system_instruction)
        self.assertIn("critical", system_instruction)
        self.assertIn("enterprise ATS", system_instruction)

        persisted = jd_manager.read_ats_classification(self.jd_path)
        self.assertEqual(persisted["provider_id"], "workday")
        self.assertEqual(persisted["weight_tier"], "enterprise_high")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_greenhouse_source_url_gets_light_touch_wording(self, mock_generate, mock_research):
        self._write_jd(source_url="https://boards.greenhouse.io/acme/jobs/123")
        self._seed_checkpoint_keywords({"tools": ["Figma"], "hard_skills": [], "core_functions": []})
        mock_generate.return_value = (self._clean_letter_json(), {})
        self._run_build()

        system_instruction = mock_generate.call_args_list[-1].kwargs["system_instruction"]
        self.assertIn("light touch", system_instruction)
        self.assertIn("human reads this first", system_instruction)

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_no_source_url_leaves_classification_unset_and_uses_unknown_tier_wording(self, mock_generate, mock_research):
        self._write_jd(source_url="")
        self._seed_checkpoint_keywords({"tools": ["Figma"], "hard_skills": [], "core_functions": []})
        mock_generate.return_value = (self._clean_letter_json(), {})
        self._run_build()

        system_instruction = mock_generate.call_args_list[-1].kwargs["system_instruction"]
        self.assertIn("helpful context", system_instruction)
        self.assertIsNone(jd_manager.read_ats_classification(self.jd_path))

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_cached_classification_is_reused_without_reclassifying(self, mock_generate, mock_research):
        self._write_jd(source_url="https://boards.greenhouse.io/acme/jobs/123")
        # save_ats_classification() rewrites the JD file, which changes
        # compute_job_key()'s content hash (jd_manager.py has no
        # source_job_id here) -- seed the checkpoint AFTER that rewrite so
        # it's keyed under the job_key build_tailored_coverletter() will
        # actually recompute from the final file bytes.
        jd_manager.save_ats_classification(self.jd_path, {"provider_id": "ashby", "weight_tier": "evidence_based"})
        self._seed_checkpoint_keywords({"tools": ["Figma"], "hard_skills": [], "core_functions": []})
        mock_generate.return_value = (self._clean_letter_json(), {})
        self._run_build()

        system_instruction = mock_generate.call_args_list[-1].kwargs["system_instruction"]
        # Cached "ashby/evidence_based" wins over what the greenhouse
        # source_url would otherwise classify to -- proves the cache is
        # actually read, not silently recomputed every build.
        self.assertIn("real evidence", system_instruction)
        self.assertEqual(jd_manager.read_ats_classification(self.jd_path)["provider_id"], "ashby")

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_no_checkpoint_keywords_triggers_on_demand_extraction(self, mock_generate, mock_research):
        self._write_jd(source_url="")
        keyword_json = json.dumps({"tools": ["Figma"], "hard_skills": [], "core_functions": []})
        mock_generate.side_effect = [(keyword_json, {}), (self._clean_letter_json(), {})]
        self._run_build()

        self.assertEqual(mock_generate.call_count, 2)
        letter_system_instruction = mock_generate.call_args_list[-1].kwargs["system_instruction"]
        self.assertIn("Figma", letter_system_instruction)
        # Extraction is in-memory only for a standalone cover-letter run --
        # no checkpoint should exist afterward.
        self.assertEqual(jd_manager.load_checkpoint(self.job_key), {})

    @patch.object(orchestrator.ResumeEngine, "research_company", return_value=None)
    @patch("orchestrator.GeminiClient.generate")
    def test_no_keywords_available_produces_no_keywords_block(self, mock_generate, mock_research):
        self._write_jd(source_url="")
        mock_generate.side_effect = [("", {}), (self._clean_letter_json(), {})]
        self._run_build()

        system_instruction = mock_generate.call_args_list[-1].kwargs["system_instruction"]
        # The prompt template's own instructions always mention the
        # "=== KEYWORDS ===" marker by name (explaining the convention, same
        # as REFERRAL's), so check for the actual injected content instead.
        self.assertNotIn("Top terms from this job description:", system_instruction)


if __name__ == "__main__":
    unittest.main()
