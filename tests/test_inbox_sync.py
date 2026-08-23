"""Unit tests for inbox_sync.py."""

import email
import email.message
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
sys.path.insert(0, SCRIPTS_DIR)

import inbox_sync  # noqa: E402
from inbox_sync import (  # noqa: E402
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


class TestSmartQuoteNormalization(unittest.TestCase):
    """Mail clients emit typographic punctuation. Every real rejection in
    the live test mailbox said "we won\u2019t be moving forward" with a curly
    apostrophe, which an ASCII "won'?t" pattern silently misses -- the
    classifier reported 'unknown' for a dozen genuine rejections."""

    def test_curly_apostrophe_rejection_is_classified(self):
        intent = classify_email_intent(
            "Update on your application for Generalist Expert",
            "After careful consideration, we won\u2019t be moving forward with your "
            "application for this role.",
        )
        self.assertEqual(intent, "rejection")

    def test_straight_apostrophe_still_works(self):
        intent = classify_email_intent(
            "Update", "we won't be moving forward with your application"
        )
        self.assertEqual(intent, "rejection")

    def test_normalizer_folds_quotes_dashes_and_nbsp(self):
        folded = inbox_sync._normalize_text("a\u2019b \u201cc\u201d d\u2013e\u00a0f")
        self.assertEqual(folded, 'a\'b "c" d-e f')


class TestApplicationGate(unittest.TestCase):
    """Without this gate the first real-mail run was useless: a rent
    reminder and a Quora digest scored as recruiter mail while genuine
    application updates scored 'unknown'."""

    def test_job_board_alert_is_rejected(self):
        self.assertFalse(
            inbox_sync.is_job_application_mail(
                "ZipRecruiter <alerts@ziprecruiter.com>",
                "Panera Bread has an open position",
            )
        )

    def test_hiring_broadcast_subject_is_rejected(self):
        self.assertFalse(
            inbox_sync.is_job_application_mail(
                "jobs@somecompany.com", "We're hiring Teacher Aides for 2026-2027"
            )
        )

    def test_newsletter_is_rejected(self):
        self.assertFalse(
            inbox_sync.is_job_application_mail(
                "The New York Times <nytdirect@nytimes.com>",
                "The Morning: Bot meets bot",
            )
        )

    def test_rent_reminder_is_rejected(self):
        self.assertFalse(
            inbox_sync.is_job_application_mail(
                "Flex <no-reply@getflex.com>", "Alex: your rent, your schedule"
            )
        )

    def test_real_application_update_passes(self):
        self.assertTrue(
            inbox_sync.is_job_application_mail(
                "Mercor <team@mercor.com>",
                "Update on your application for Generalist Expert",
            )
        )

    def test_ats_sender_passes(self):
        self.assertTrue(
            inbox_sync.is_job_application_mail(
                "no-reply@greenhouse.io", "A note about your candidacy"
            )
        )

    def test_known_company_sender_passes(self):
        known = {inbox_sync._normalize_company("Rula")}
        self.assertTrue(
            inbox_sync.is_job_application_mail(
                "careers@rula.com", "Following up", known_companies=known
            )
        )

    def test_application_phrase_in_body_alone_does_not_pass(self):
        """Newsletters bury these phrases in footers constantly, so the
        phrase only counts in the SUBJECT."""
        self.assertFalse(
            inbox_sync.is_job_application_mail(
                "news@marketing.com",
                "Weekly digest",
                body="...thank you for applying to our newsletter...",
            )
        )


class TestGateFiltersResults(unittest.TestCase):

    def test_non_application_mail_is_dropped_entirely(self):
        messages = [
            {
                "from": "nytdirect@nytimes.com",
                "subject": "The Morning",
                "body": "unfortunately",
                "date": "",
            },
            {
                "from": "team@mercor.com",
                "subject": "Update on your application for X",
                "body": "we won't be moving forward with your application",
                "date": "",
            },
        ]

        results = process_email_messages(messages)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["intent"], "rejection")


class TestBareUnfortunatelyIsNotARejection(unittest.TestCase):
    """A Quora digest scored 'rejection' on the first real run purely
    because its body contained the word "unfortunately"."""

    def test_prose_using_unfortunately_is_unknown(self):
        intent = classify_email_intent(
            "My vet killed my cat",
            "Unfortunately the appointment did not go well at all.",
        )
        self.assertEqual(intent, "unknown")

    def test_unfortunately_we_is_still_a_rejection(self):
        intent = classify_email_intent(
            "Update", "Unfortunately, we have decided to pursue other candidates."
        )
        self.assertEqual(intent, "rejection")


class TestATSDomainSuffixMatching(unittest.TestCase):
    """Real ATS mail is overwhelmingly subdomained. Matching on
    domain.split(".")[0] read "talent.icims.com" as "talent" and failed
    every one of them -- the single largest source of missed job mail
    (23% recall against hand-labeled folders before the fix)."""

    def test_subdomained_ats_senders_match(self):
        for domain in (
            "talent.icims.com",
            "mail.paylocity.com",
            "app.bamboohr.com",
            "hire.lever.co",
            "otp.workday.com",
        ):
            self.assertTrue(inbox_sync._is_ats_domain(domain), domain)

    def test_bare_ats_domain_matches(self):
        self.assertTrue(inbox_sync._is_ats_domain("mercor.com"))

    def test_unrelated_domain_does_not_match(self):
        for domain in ("nytimes.com", "getflex.com", "noticims.com"):
            self.assertFalse(inbox_sync._is_ats_domain(domain), domain)

    def test_lookalike_suffix_does_not_match(self):
        """ "evilicims.com" must not match "icims.com"."""
        self.assertFalse(inbox_sync._is_ats_domain("evilicims.com"))


class TestNonJobContextExclusion(unittest.TestCase):
    """Rental, tuition and banking mail uses identical vocabulary. A
    leasing portal's "Complete your application" was the most persistent
    false positive across several rounds of tightening."""

    def test_rental_application_is_rejected(self):
        self.assertFalse(
            inbox_sync.is_job_application_mail(
                "Flex <no-reply@getflex.com>",
                "Reminder: Complete your application",
                body="Complete your Flex application to split rent on your apartment.",
            )
        )

    def test_tuition_application_is_rejected(self):
        self.assertFalse(
            inbox_sync.is_job_application_mail(
                "billing@theparkschool.org",
                "Your application status",
                body="Your tuition assistance application is past due.",
            )
        )

    def test_real_job_application_still_passes(self):
        self.assertTrue(
            inbox_sync.is_job_application_mail(
                "careers@rula.com",
                "Update on your application",
                body="Thank you for applying to the Lifecycle Manager role.",
            )
        )


class TestOfferRequiresAnActualOffer(unittest.TestCase):
    """Recruiter outreach says "are you available to talk about my ...
    job offer", which is a pitch for an opening, not an offer extended
    to the candidate."""

    def test_recruiter_pitch_is_not_an_offer(self):
        intent = classify_email_intent(
            "Alex, are you available?",
            "are you available to talk about my Sales Consultant job offer",
        )
        self.assertNotEqual(intent, "offer")

    def test_genuine_offer_is_an_offer(self):
        self.assertEqual(
            classify_email_intent("Good news", "We are pleased to offer you the role."),
            "offer",
        )
        self.assertEqual(
            classify_email_intent("Docs", "Please find your offer letter attached."),
            "offer",
        )


class TestTrustedLabelFolders(unittest.TestCase):
    """Gmail exposes labels as IMAP folders. A label the user applied by
    hand beats any pattern, and covers the recruiter back-and-forth the
    gate structurally cannot recognise."""

    def test_trust_all_bypasses_the_gate(self):
        # A thread with a person, on a domain nothing recognises, whose
        # subject carries no application vocabulary -- ungateable by
        # construction, and exactly what a hand-applied label is for.
        messages = [
            {
                "from": "hiring.lead@some-startup.example",
                "subject": "Re: Thursday",
                "body": "Great chatting -- let's pick this up next week.",
                "date": "",
            }
        ]

        self.assertEqual(len(process_email_messages(messages)), 0)
        self.assertEqual(len(process_email_messages(messages, trust_all=True)), 1)

    def test_known_staffing_thread_now_passes_the_gate_unaided(self):
        """This used to need a label. Recruiter-domain detection reaches
        it directly."""
        messages = [
            {
                "from": "recruiter@artech.com",
                "subject": "RE: ArtechOBGC//IBM_Amex//Alex Rivera",
                "body": "Following up on the role we discussed.",
                "date": "",
            }
        ]

        results = process_email_messages(messages)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["intent"], "recruiter_outreach")

    def test_job_label_folders_are_declared(self):
        self.assertIn("Job Applications", inbox_sync.JOB_LABEL_FOLDERS)
        self.assertIn("Job Interviews", inbox_sync.JOB_LABEL_FOLDERS)


class TestRecruiterDetection(unittest.TestCase):
    """Staffing-agency threads are human-written, from non-ATS domains,
    with no application vocabulary in the subject -- the category the
    phrase gate structurally could not reach."""

    def test_known_staffing_domain(self):
        self.assertTrue(
            inbox_sync.is_recruiter_outreach("k@artech.com", "Anything", "")
        )

    def test_subdomain_of_staffing_firm(self):
        self.assertTrue(
            inbox_sync.is_recruiter_outreach("k@mail.axelon.com", "Anything", "")
        )

    def test_self_identification_from_an_unknown_domain(self):
        self.assertTrue(
            inbox_sync.is_recruiter_outreach(
                "dan@some-agency.example",
                "Opportunity",
                "My name is Dan and I am a recruiter at Some Agency.",
            )
        )

    def test_resume_discovery_phrase(self):
        self.assertTrue(
            inbox_sync.is_recruiter_outreach(
                "x@unknown.example",
                "Role",
                "I came across your resume on a job portal.",
            )
        )

    def test_structured_position_fields(self):
        body = "Position ID: 123\nJob Title: Designer\nDuration: 6 Months\n"
        self.assertTrue(
            inbox_sync.is_recruiter_outreach("x@unknown.example", "Role", body)
        )

    def test_a_single_field_is_not_enough(self):
        self.assertFalse(
            inbox_sync.is_recruiter_outreach(
                "x@unknown.example", "Note", "Location: Buffalo, NY"
            )
        )

    def test_newsletter_is_not_recruiter_mail(self):
        self.assertFalse(
            inbox_sync.is_recruiter_outreach(
                "nytdirect@nytimes.com", "The Morning", "Bot meets bot"
            )
        )

    def test_recruiter_outreach_is_its_own_intent(self):
        intent = classify_email_intent(
            "Job Opportunity :: Buffalo", "I came across your resume.", "k@artech.com"
        )
        self.assertEqual(intent, "recruiter_outreach")

    def test_a_real_outcome_beats_outreach(self):
        """A recruiter thread that reached a rejection reports the
        rejection, not fresh outreach."""
        intent = classify_email_intent(
            "Update",
            "I came across your resume. Unfortunately, we are not moving forward.",
            "k@artech.com",
        )
        self.assertEqual(intent, "rejection")


class TestNonJobDomains(unittest.TestCase):

    def test_leasing_and_school_domains_are_rejected(self):
        for domain in ("assist.rent", "mjpeterson.com", "williamsvillek12.org"):
            self.assertTrue(inbox_sync._is_non_job_domain(domain), domain)

    def test_normal_company_is_not(self):
        self.assertFalse(inbox_sync._is_non_job_domain("rula.com"))

    def test_gate_rejects_a_non_job_domain_outright(self):
        self.assertFalse(
            inbox_sync.is_job_application_mail(
                "leasing@mjpeterson.com", "Your application has been received"
            )
        )


class TestSentClassification(unittest.TestCase):

    def test_follow_up_beats_application(self):
        """A follow-up restates the application it chases; the chase is
        the newer fact."""
        intent = inbox_sync.classify_sent_intent(
            "Checking in",
            "I'm writing to check on the status of my application for the SDR role.",
        )
        self.assertEqual(intent, "follow_up")

    def test_direct_application(self):
        self.assertEqual(
            inbox_sync.classify_sent_intent(
                "SDR role", "I applied for the Senior SDR role and wanted to say hi."
            ),
            "application",
        )

    def test_cold_outreach(self):
        self.assertEqual(
            inbox_sync.classify_sent_intent(
                "Hello", "I wanted to reach out directly and introduce myself."
            ),
            "outreach",
        )

    def test_ordinary_mail_is_unknown(self):
        self.assertEqual(
            inbox_sync.classify_sent_intent("Lunch?", "Are you free Thursday?"),
            "unknown",
        )


class TestApplicationsWithoutReplies(unittest.TestCase):
    """The one signal the inbox cannot produce: a silent rejection looks
    identical to an application that was never sent."""

    def test_domain_with_no_inbound_mail_is_reported(self):
        sent = [{"domain": "allego.com", "intent": "application", "subject": "x"}]
        received = [{"from": "careers@rula.com"}]

        silent = inbox_sync.applications_without_replies(sent, received)

        self.assertEqual(len(silent), 1)
        self.assertEqual(silent[0]["domain"], "allego.com")

    def test_domain_that_replied_is_not_reported(self):
        sent = [{"domain": "allego.com", "intent": "application", "subject": "x"}]
        received = [{"from": "recruiting@allego.com"}]

        self.assertEqual(inbox_sync.applications_without_replies(sent, received), [])

    def test_cold_outreach_is_not_counted_as_an_application(self):
        sent = [{"domain": "allego.com", "intent": "outreach", "subject": "x"}]

        self.assertEqual(inbox_sync.applications_without_replies(sent, []), [])


if __name__ == "__main__":
    unittest.main()


def _raw(subject: str, body: str, content_type: str = "text/plain") -> bytes:
    msg = email.message.EmailMessage()
    msg["From"] = "recruiter@rula.com"
    msg["Subject"] = subject
    msg["Date"] = "Tue, 19 Aug 2026 10:00:00 -0400"
    if content_type == "text/html":
        msg.set_content(body, subtype="html")
    else:
        msg.set_content(body)
    return msg.as_bytes()


class TestHeaderDecoding(unittest.TestCase):
    """Recruiter subjects are routinely RFC 2047 encoded. Classifying the
    raw '=?utf-8?q?...?=' form matches nothing and silently buckets real
    interview requests as 'unknown'."""

    def test_encoded_subject_is_decoded(self):
        encoded = "=?utf-8?q?Interview_Request=3A_Acme?="
        self.assertEqual(inbox_sync._decode(encoded), "Interview Request: Acme")

    def test_plain_subject_passes_through(self):
        self.assertEqual(inbox_sync._decode("Plain Subject"), "Plain Subject")

    def test_missing_header_is_empty_string(self):
        self.assertEqual(inbox_sync._decode(None), "")


class TestBodyExtraction(unittest.TestCase):

    def test_plain_text_body(self):
        msg = email.message_from_bytes(_raw("s", "We would like to interview you."))
        self.assertIn("interview", inbox_sync._body_text(msg))

    def test_html_only_body_is_stripped_to_text(self):
        """Plenty of ATS mail is HTML-only; skipping it would blind the
        classifier to exactly the messages that matter."""
        html = "<html><body><p>Unfortunately</p><b>not moving forward</b></body></html>"
        msg = email.message_from_bytes(_raw("s", html, content_type="text/html"))
        text = inbox_sync._body_text(msg)

        self.assertIn("not moving forward", text)
        self.assertNotIn("<b>", text)

    def test_script_and_style_contents_are_removed(self):
        html = "<html><style>p{color:red}</style><p>interview</p></html>"
        msg = email.message_from_bytes(_raw("s", html, content_type="text/html"))
        text = inbox_sync._body_text(msg)

        self.assertIn("interview", text)
        self.assertNotIn("color:red", text)


class TestCompanyNormalization(unittest.TestCase):

    def test_legal_suffixes_and_punctuation_are_folded(self):
        self.assertEqual(
            inbox_sync._normalize_company("Rula, Inc."),
            inbox_sync._normalize_company("rula"),
        )

    def test_distinct_companies_do_not_collapse(self):
        self.assertNotEqual(
            inbox_sync._normalize_company("Stripe"),
            inbox_sync._normalize_company("Strava"),
        )


class TestCompanyMatching(unittest.TestCase):

    JOBS = [
        {
            "id": "1",
            "title": "Lifecycle Manager",
            "company": "Rula",
            "status": "applied",
        },
        {
            "id": "2",
            "title": "Content Strategist",
            "company": "Stripe",
            "status": "pending",
        },
    ]

    def test_exact_normalized_match(self):
        matches = inbox_sync.match_company_to_jobs("Rula, Inc.", self.JOBS)
        self.assertEqual([m["id"] for m in matches], ["1"])

    def test_unknown_company_matches_nothing(self):
        self.assertEqual(
            inbox_sync.match_company_to_jobs("Unknown Company", self.JOBS), []
        )

    def test_empty_company_matches_nothing(self):
        self.assertEqual(inbox_sync.match_company_to_jobs("", self.JOBS), [])

    def test_unrelated_company_matches_nothing(self):
        """A rejection attached to the wrong application is worse than no
        match at all, so matching stays conservative."""
        self.assertEqual(inbox_sync.match_company_to_jobs("Netflix", self.JOBS), [])


class TestATSSenderHandling(unittest.TestCase):

    def test_ats_domain_does_not_become_the_company(self):
        company = extract_company_from_email(
            "Rula Recruiting <no-reply@greenhouse.io>", "Your application to Rula"
        )
        self.assertNotEqual(company.lower(), "greenhouse")

    def test_real_company_domain_is_used(self):
        self.assertEqual(
            extract_company_from_email("careers@rula.com", "Next steps"), "Rula"
        )


class TestConnectCredentials(unittest.TestCase):

    def test_missing_credentials_raise_an_actionable_error(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("inbox_sync.load_dotenv"):
                with self.assertRaises(RuntimeError) as ctx:
                    inbox_sync.connect()

        self.assertIn("GMAIL_APP_PASSWORD", str(ctx.exception))

    def test_login_failure_explains_the_app_password_requirement(self):
        import imaplib

        fake = MagicMock()
        fake.login.side_effect = imaplib.IMAP4.error("AUTHENTICATIONFAILED")

        with patch("inbox_sync.load_dotenv"):
            with patch.dict(
                os.environ,
                {"GMAIL_ADDRESS": "a@b.com", "GMAIL_APP_PASSWORD": "x"},
                clear=True,
            ):
                with patch("imaplib.IMAP4_SSL", return_value=fake):
                    with self.assertRaises(RuntimeError) as ctx:
                        inbox_sync.connect()

        self.assertIn("app password", str(ctx.exception).lower())


class TestProcessEmailMessages(unittest.TestCase):

    def test_results_carry_matched_jobs(self):
        messages = [
            {
                "from": "careers@rula.com",
                "subject": "Interview request for Lifecycle Manager",
                "body": "We would like to schedule an interview with you.",
                "date": "",
            }
        ]
        jobs = [
            {
                "id": "1",
                "title": "Lifecycle Manager",
                "company": "Rula",
                "status": "applied",
            }
        ]

        results = process_email_messages(messages, jobs=jobs)

        self.assertEqual(results[0]["intent"], "interview")
        self.assertEqual(results[0]["matched_jobs"][0]["id"], "1")

    def test_writes_nothing_without_jobs(self):
        messages = [
            {
                "from": "x@y.com",
                "subject": "Update on your application",
                "body": "hello",
                "date": "",
            }
        ]
        results = process_email_messages(messages)

        self.assertEqual(results[0]["matched_jobs"], [])


class TestRejectionBeatsInterview(unittest.TestCase):
    """A rejection often contains the word 'interview' ("thank you for
    interviewing with us"), so rejection must be tested first."""

    def test_rejection_mentioning_interview_is_a_rejection(self):
        intent = classify_email_intent(
            "Update on your application",
            "Thank you for interviewing with us. Unfortunately we are not moving "
            "forward with your candidacy.",
        )
        self.assertEqual(intent, "rejection")


if __name__ == "__main__":
    unittest.main()
