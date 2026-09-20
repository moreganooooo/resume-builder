import unittest
from unittest.mock import patch

from scripts.answer_grounding import check_answer
from scripts.answer_questions import QuestionKind
from scripts.application_answers import (
    AnswerContext,
    AnswerResult,
    Evidence,
    render_prompt,
)


class TestApplicationAnswersEngine(unittest.TestCase):
    def test_prompt_is_bounded_and_contains_history_last(self):
        context = AnswerContext("id", "Role", "Acme", "JD text")
        prompt = render_prompt(
            context,
            Evidence("verified evidence"),
            [{"role": "user", "text": "shorter"}],
            "Why this role?",
            QuestionKind.WHY_ROLE,
            250,
        )
        self.assertIn("shorter", prompt)
        self.assertIn("250 characters", prompt)
        self.assertLessEqual(len(prompt), 60000)

    def test_invented_number_is_flagged_but_jd_number_passes(self):
        context = AnswerContext("id", "Role", "Acme", "The team grew 12 people.")
        evidence = Evidence("Built a 12-person team.")
        self.assertFalse(check_answer("I built a 12-person team.", context, evidence))
        self.assertTrue(check_answer("I improved results by 40%.", context, evidence))

    def test_answer_retries_hard_grounding_violation(self):
        context = AnswerContext("id", "Role", "Acme", "The team grew 12 people.")
        with (
            patch("scripts.application_answers.build_context", return_value=context),
            patch(
                "scripts.application_answers.evidence_for",
                return_value=Evidence("12 people"),
            ),
            patch(
                "scripts.application_answers._generate",
                side_effect=["I improved results by 40%.", "I built a 12-person team."],
            ) as generate,
        ):
            from scripts.application_answers import answer

            result = answer("id", "Describe your impact.")
        self.assertEqual(result.text, "I built a 12-person team.")
        self.assertEqual(generate.call_count, 2)


if __name__ == "__main__":
    unittest.main()
