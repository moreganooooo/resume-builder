"""Unit tests for inbox_sync.py."""

import unittest

from inbox_sync import (
    classify_email_intent,
    extract_company_from_email,
    process_email_messages,
)


class TestInboxSync(unittest.TestCase):

    def test_classify_email_intent(self):
        self.assertEqual(
            classify_email_intent(
                "Interview Request: Acme Software Engineer",
                "We'd love to schedule a time to chat with you for next steps.",
            ),
            "interview",
        )
        self.assertEqual(
            classify_email_intent(
                "Update on your application",
                "Unfortunately, we are pursuing other candidates at this time.",
            ),
            "rejection",
        )
        self.assertEqual(
            classify_email_intent(
                "Job Offer - Senior Engineer",
                "We are pleased to offer you the position of Senior Engineer.",
            ),
            "offer",
        )
        self.assertEqual(
            classify_email_intent(
                "Application Received",
                "Thank you for applying to Google. We have received your application.",
            ),
            "acknowledgment",
        )

    def test_extract_company_from_email(self):
        self.assertEqual(
            extract_company_from_email(
                "Jane Doe <jane@airbnb.com>", "Your application"
            ),
            "Airbnb",
        )
        self.assertEqual(
            extract_company_from_email(
                "recruiter@gmail.com", "Interview with Acme Corp - Next Steps"
            ),
            "Acme Corp",
        )

    def test_process_email_messages(self):
        msgs = [
            {
                "from": "recruiter@stripe.com",
                "subject": "Interview scheduling",
                "body": "Let's schedule a phone screen",
            }
        ]
        results = process_email_messages(msgs)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["company"], "Stripe")
        self.assertEqual(results[0]["intent"], "interview")


if __name__ == "__main__":
    unittest.main()
