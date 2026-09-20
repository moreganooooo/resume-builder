import unittest

from scripts.answer_questions import QuestionKind, classify_question, sensitive_response


class TestAnswerQuestions(unittest.TestCase):
    def test_sensitive_and_specific_categories(self):
        cases = {
            "Do you require visa sponsorship now or later?": QuestionKind.LEGAL,
            "Are you legally authorized to work in the US?": QuestionKind.LEGAL,
            "What are your salary expectations?": QuestionKind.SALARY,
            "Why do you want to work at Acme?": QuestionKind.WHY_COMPANY,
            "Why are you interested in this role?": QuestionKind.WHY_ROLE,
            "Tell me about a time you disagreed with a teammate.": QuestionKind.BEHAVIORAL,
            "How many years have you used Salesforce?": QuestionKind.EXPERIENCE_WITH_TOOL,
            "Do you identify as a veteran?": QuestionKind.EEO,
        }
        for question, expected in cases.items():
            with self.subTest(question=question):
                self.assertEqual(classify_question(question), expected)

    def test_sensitive_response_is_deterministic(self):
        self.assertIn(
            "answer this question yourself", sensitive_response(QuestionKind.EEO, {})
        )
        self.assertEqual(
            sensitive_response(
                QuestionKind.LEGAL,
                {"application_answers": {"work_authorization": "Yes"}},
            ),
            "Yes",
        )

    def test_unknown_is_general(self):
        self.assertEqual(
            classify_question("What is your favorite project?"), QuestionKind.GENERAL
        )


if __name__ == "__main__":
    unittest.main()
