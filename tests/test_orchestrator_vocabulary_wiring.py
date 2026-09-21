import os
import sys
import unittest

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import company_research  # noqa: E402
import orchestrator  # noqa: E402


class TestVocabularyWiringContract(unittest.TestCase):
    """build_tailored_resume applies vocabulary substitutions from the
    checkpoint (not from an in-scope `research` variable) so a resumed run
    behaves identically to a fresh one -- `research` is assigned only in
    the fresh-build branch."""

    def test_substitution_reads_from_checkpoint_not_research_variable(self):
        engine = orchestrator.ResumeEngine
        # Step 2b persists the substitutions to the checkpoint...
        mining = orchestrator.inspect.getsource(engine._mine_and_research)
        self.assertIn('checkpoint["vocabulary_substitutions"]', mining)
        # ...and the finalize step reads them back from the checkpoint.
        finalize = orchestrator.inspect.getsource(engine._finalize_resume_text)
        self.assertIn("apply_vocabulary_substitutions_to_resume", finalize)
        self.assertIn('checkpoint.get("vocabulary_substitutions"', finalize)
        self.assertNotIn("research", finalize.split("def ", 2)[1].split(")")[0])

    def test_substitution_runs_before_the_save_step(self):
        source = orchestrator.inspect.getsource(
            orchestrator.ResumeEngine.build_tailored_resume
        )
        subst_at = source.index("self._finalize_resume_text(")
        save_at = source.index("# --- Step 6: Save output ---")
        self.assertLess(subst_at, save_at)

    def test_end_to_end_substitution_on_a_built_resume_shape(self):
        resume_data = {
            "SUMMARY": "Strategist",
            "EXPERIENCE": [
                {"company": "Acme", "achievements": ["Grew customers by 30%"]}
            ],
        }
        pairs = [{"generic_term": "customers", "company_term": "guests"}]
        result = company_research.apply_vocabulary_substitutions_to_resume(
            resume_data, pairs
        )
        self.assertEqual(
            result["EXPERIENCE"][0]["achievements"][0], "Grew guests by 30%"
        )


if __name__ == "__main__":
    unittest.main()
