"""
inbox_sync.py — Email / IMAP recruiter status sync.

Reads a mailbox over IMAP, classifies each message as an interview
request, offer, rejection, or acknowledgment, and matches it against the
jobs in this profile's database.

Scope note: this module currently REPORTS what it finds and writes
nothing back. Proving the classifier against real mail comes first --
auto-transitioning an application's status on a regex match would be a
bad thing to get wrong silently. `sync_inbox()` returns the matched
results so a caller (or a later --apply mode) can act on them.

Credentials come from the active profile's own .env (see
profile_paths.env_path), never a shared project-root one:

    GMAIL_ADDRESS=you@gmail.com
    GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
    # optional, defaults below
    IMAP_HOST=imap.gmail.com
    IMAP_FOLDER=INBOX

Gmail rejects an account password here; the app password is a 16-character
credential generated at https://myaccount.google.com/apppasswords and
requires 2-Step Verification to be on.
"""

from __future__ import annotations

import argparse
import email
import email.utils
import imaplib
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from typing import Any, Dict, List, Optional

import cli_art
import db
import profile_paths
from dotenv import load_dotenv

DEFAULT_IMAP_HOST = "imap.gmail.com"
DEFAULT_FOLDER = "INBOX"

# Gmail exposes each label as an IMAP folder, so a label the user has
# already applied by hand is directly readable -- and is far better
# evidence than any pattern. Mail in these folders bypasses the gate
# entirely.
#
# This matters because the gate has a real ceiling: measured against
# these very folders, it recovers about half of them, and most of what it
# misses is recruiter back-and-forth ("RE: ArtechOBGC//IBM_Amex//Alex
# Mercer") that is recognisable only from conversational context. A human
# already made that judgement; reading the label is how we inherit it.
JOB_LABEL_FOLDERS = (
    "Job Applications",
    "Job Interviews",
    "Job Rejections :(",
)

# Registrable domains of applicant-tracking systems and staffing firms.
#
# Stored as FULL domains and matched by suffix, not as bare first labels.
# The previous version compared domain.split(".")[0], which reads
# "talent.icims.com" as "talent" and "mail.paylocity.com" as "mail" -- so
# every subdomained ATS sender failed the gate, and real ATS mail is
# overwhelmingly subdomained. That single bug was the largest source of
# missed job mail (measured against hand-labeled Gmail folders: 23%
# recall on "Job Applications" before the fix).
#
# Domains below Tier 1 come from an inventory of this user's own inbox
# rather than a generic list, so they reflect ATSes actually in use.
ATS_DOMAINS = {
    # Major platforms
    "greenhouse.io",
    "eu.greenhouse.io",
    "greenhouse-mail.io",
    "lever.co",
    "ashbyhq.com",
    "workday.com",
    "myworkday.com",
    "smartrecruiters.com",
    "icims.com",
    "jobvite.com",
    "taleo.net",
    "successfactors.com",
    "bamboohr.com",
    "workable.com",
    "rippling.com",
    "breezy.hr",
    "paylocity.com",
    "cadienttalent.com",
    "careerbuilder.com",
    "jobright.com",
    "dice.com",
    # Staffing and recruiting firms
    "roberthalf.com",
    "aquent.com",
    "allego.com",
    "spectraforce.com",
    "maxeleven.com",
    "tanishasystems.com",
    "ustechsolutionsinc.com",
    "timeetc.com",
    "jobmail.io",
    # Evaluation / gig platforms this user applies through
    "mercor.com",
    "c-mercor.com",
    "usertesting.com",
    "telusinternational.ai",
}


def _is_employer_ats(domain: str) -> bool:
    """True for platforms that are their own employer (see the set)."""
    domain = (domain or "").lower().strip(".")
    return any(
        domain == ats or domain.endswith("." + ats) for ats in ATS_IS_ALSO_EMPLOYER
    )


def _is_ats_domain(domain: str) -> bool:
    """Suffix match, so a subdomain of a known ATS still counts."""
    domain = (domain or "").lower().strip(".")
    return any(domain == ats or domain.endswith("." + ats) for ats in ATS_DOMAINS)


# Contexts that use application/interview vocabulary for something that is
# not a job. Every one of these is present in this user's mailbox --
# rental applications from a leasing portal were the single most persistent
# false positive, surviving several rounds of tightening.
NON_JOB_CONTEXT = re.compile(
    r"\b(apartment|rental|renters?|lease|landlord|property manager|"
    r"split rent|tuition|financial aid|scholarship|enrollment|"
    r"student loan|mortgage|credit card|checking account|"
    r"insurance (quote|policy)|membership application|"
    r"transportation inquiry|bus (route|stop)|school district|"
    r"parent[- ]teacher|field trip)\b",
    re.I,
)

CONSUMER_DOMAINS = {
    "gmail",
    "yahoo",
    "outlook",
    "hotmail",
    "icloud",
    "mail",
    "protonmail",
    "aol",
}


# Bulk senders that mail about jobs but never about YOUR application:
# job boards pushing alerts, and newsletters about job hunting. Their
# messages are full of the same vocabulary a real status update uses.
ALERT_SENDERS = (
    "ziprecruiter",
    "jobalerts",
    "job-alerts",
    "indeedemail",
    "indeed.com",
    "glassdoor",
    "linkedin.com",
    "monster",
    "careerbuilder",
    "dice.com",
    "builtin",
    "wellfound",
    "angel.co",
)

# Subject shapes that mark a broadcast about openings rather than a
# response to something you sent.
ALERT_SUBJECT = re.compile(
    r"(new jobs?\b|jobs? alert|job alerts?|is hiring|we'?re hiring|"
    r"open positions?|jobs? for you|recommended for you|"
    r"\d+\+? new jobs|apply now|hiring now|job of the day)",
    re.I,
)

# Phrases that only appear when a message is ABOUT an application the
# candidate already submitted.
APPLICATION_SUBJECT = re.compile(
    r"(your application|application (for|to|status|update|submitted|received)|"
    r"update on your application|regarding your application|"
    r"thank you (for )?(your )?appl(ying|ication)|application received|"
    r"your candidacy|your submission|you'?ve applied|you have applied|"
    r"interview (invitation|request|scheduling|confirmation|with)|"
    r"next steps|schedule (an|your) interview|phone screen|"
    r"you are invited|invitation:|"
    r"position:|role:|"
    r"we would like to (speak|meet|talk|schedule))",
    re.I,
)


def _sender_domain(from_header: str) -> str:
    match = re.search(r"@([\w.\-]+)", from_header or "")
    return match.group(1).lower() if match else ""


# Staffing and contract-recruiting firms. Distinct from ATS_DOMAINS:
# an ATS sends automated status mail about an application you submitted,
# whereas these are humans pitching roles at you. Both are job mail, but
# they mean opposite things for the pipeline.
RECRUITER_DOMAINS = {
    "artech.com",
    "axelon.com",
    "authentic-staffing.com",
    "staffgreat.com",
    "collabera.com",
    "teksystems.com",
    "adecco.com",
    "manpower.com",
    "kellyservices.com",
    "dexian.com",
    "roseint.com",
    "randstad.com",
    "apexsystems.com",
    "insightglobal.com",
    "motionrecruitment.com",
    "beacontalent.com",
}

# How a recruiter opens a cold email. These are strong signals precisely
# because no automated ATS message and no newsletter phrases itself this
# way -- someone is telling you who they are and where they found you.
RECRUITER_PHRASES = re.compile(
    r"("
    r"i'?m a (technical |senior )?recruiter|i am a (technical |senior )?recruiter|"
    r"recruiter (at|with|for)|recruiting team|staffing agency|"
    r"talent acquisition|technical recruiter|staffing a |"
    r"came across your resume|found your resume|noticed your resume|"
    r"saw your background|reviewed your profile|your resume (which was )?posted|"
    r"potential candidates"
    r")",
    re.I,
)

# Recruiters paste a structured role spec. Two or more of these fields in
# one message is a shape ordinary mail does not have.
RECRUITER_FIELDS = re.compile(
    r"^\s*(position id|job id|job title|duration|shift timing|client|"
    r"pay rate|pay|rate|location|employment type|work authorization)\s*:",
    re.I | re.M,
)


# Correspondents that use application/interview vocabulary but are never
# about a job for this user: leasing offices, property managers, a school
# district, a county government. Cheaper and far more reliable than trying
# to infer it from body text, which is how they kept slipping through.
NON_JOB_DOMAINS = {
    "assist.rent",
    "mjpeterson.com",
    "buffalobestwestern.com",
    "getflex.com",
    "williamsvillek12.org",
    "erie.gov",
    "theparkschool.org",
    "tabbank.com",
}


def _is_non_job_domain(domain: str) -> bool:
    domain = (domain or "").lower().strip(".")
    return any(domain == bad or domain.endswith("." + bad) for bad in NON_JOB_DOMAINS)


def is_recruiter_outreach(from_header: str, subject: str, body: str = "") -> bool:
    """True when a human is pitching a role, rather than an ATS reporting
    on an application.

    This is the category the phrase-based gate structurally cannot reach:
    measured against hand-labeled folders, the misses were almost all
    staffing-agency threads ("RE: ArtechOBGC//IBM_Amex//Alex Mercer")
    whose subjects carry no application vocabulary at all.
    """
    domain = _sender_domain(from_header)
    if any(domain == rec or domain.endswith("." + rec) for rec in RECRUITER_DOMAINS):
        return True

    text = _normalize_text(f"{subject} {body}")
    if RECRUITER_PHRASES.search(text):
        return True

    return len(RECRUITER_FIELDS.findall(body or "")) >= 2


def is_job_application_mail(
    from_header: str,
    subject: str,
    body: str = "",
    known_companies: Optional[set] = None,
) -> bool:
    """Gate: is this message plausibly about an application this person
    actually submitted?

    Classifying intent without this gate is what made the first real-mail
    run useless: a rent reminder ("...your schedule...availability") and a
    Quora digest ("unfortunately") both scored as recruiter mail, while a
    genuine "Update on your application for Generalist Expert" from Mercor
    scored 'unknown'. Marketing copy reuses every word the intent
    patterns look for, so intent alone cannot separate them.

    A message passes when it comes from a known ATS, from a company the
    profile has actually applied to, or carries an unambiguous
    application phrase in its SUBJECT (not its body -- footers and
    newsletters bury these phrases in body text constantly).

    Job-board alert blasts are rejected outright even when they match,
    since "new jobs for you" mail is about openings, not about you.
    """
    domain = _sender_domain(from_header)
    subject = _normalize_text(subject)

    if _is_non_job_domain(domain):
        return False
    if any(alert in domain for alert in ALERT_SENDERS):
        return False
    if ALERT_SUBJECT.search(subject):
        return False

    # Rental, tuition, and banking mail uses identical vocabulary. Checked
    # against subject AND body, unlike the application phrases below --
    # a leasing portal's "Complete your application" subject only reveals
    # itself as non-job further down.
    if NON_JOB_CONTEXT.search(subject) or NON_JOB_CONTEXT.search(
        _normalize_text(body)[:2000]
    ):
        return False

    if _is_ats_domain(domain):
        return True

    if is_recruiter_outreach(from_header, subject, body):
        return True

    if known_companies:
        root = domain.split(".")[0] if domain else ""
        normalized = _normalize_company(root)
        if normalized and normalized in known_companies:
            return True

    return bool(APPLICATION_SUBJECT.search(subject))


# Mail clients emit typographic punctuation, so "won\u2019t be moving forward"
# does not match a pattern written as "won'?t". Every real Mercor
# rejection in the test mailbox was missed for exactly this reason --
# the intent regexes are ASCII, so the text has to be too.
_PUNCT_MAP = str.maketrans(
    {
        "\u2019": "'",
        "\u2018": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2013": "-",
        "\u2014": "-",
        "\u00a0": " ",
    }
)


def _normalize_text(text: str) -> str:
    """Folds typographic punctuation to ASCII and collapses whitespace."""
    return " ".join((text or "").translate(_PUNCT_MAP).split())


def classify_email_intent(subject: str, body: str, from_header: str = "") -> str:
    """Classifies a message into 'offer', 'rejection', 'interview',
    'acknowledgment', 'recruiter_outreach', or 'unknown'.

    Order matters: rejection is tested before interview because rejections
    routinely say "thank you for interviewing with us", and
    recruiter_outreach is tested last so a recruiter thread that reached a
    real outcome reports that outcome instead.
    """
    text = _normalize_text(f"{subject} {body}").lower()

    # "job offer" alone is not enough: recruiter outreach routinely says
    # "are you available to talk about my ... job offer", which is a
    # pitch for an opening, not an offer extended to the candidate.
    if re.search(
        r"\b(offer of employment|employment offer|pleased to offer|"
        r"formal offer|offer letter|excited to offer you|"
        r"we would like to offer you|extend(ing)? (you )?an offer)\b",
        text,
    ):
        return "offer"
    # NB: no bare "unfortunately" here. It appears in ordinary prose
    # constantly (a Quora digest scored as a rejection on the first real
    # run) and carries no application signal on its own.
    if re.search(
        r"\b(not moving forward|other candidates|not selected|"
        r"pursuing other|decided to move forward with|will not be proceeding|"
        r"not to move forward|won'?t be moving forward|"
        r"position has been filled|no longer under consideration|"
        r"unfortunately,? we)\b",
        text,
    ):
        return "rejection"
    if re.search(
        r"\b(phone screen|coding challenge|technical assessment|"
        r"schedule (an|your) interview|interview (invitation|request|with)|"
        r"invite you to interview|like to interview|set up (a|an) (call|interview)|"
        r"next steps in the (process|interview)|hiring manager would like)\b",
        text,
    ):
        return "interview"
    if re.search(
        r"\b(application received|thank you for applying|received your application|we have received)\b",
        text,
    ):
        return "acknowledgment"

    # Checked last, so a recruiter thread that has progressed to a real
    # interview or rejection is reported as that, not as fresh outreach.
    if is_recruiter_outreach(from_header or "", subject, body):
        return "recruiter_outreach"

    return "unknown"


# Platforms that are BOTH the applicant-tracking system and the employer
# you applied to. Treating these as pure ATS infrastructure erased the
# company: every Mercor rejection came back as "Unknown Company" once
# mercor.com was added to ATS_DOMAINS, which broke matching for the
# largest single source of real status mail in this mailbox.
ATS_IS_ALSO_EMPLOYER = {
    "mercor.com",
    "c-mercor.com",
    "usertesting.com",
    "telusinternational.ai",
    "jobright.com",
}

# "...your application to Aquent | Skill", "...interest in X at Acme".
# Used when the sender domain is ATS infrastructure and therefore names
# the platform rather than the employer.
COMPANY_IN_SUBJECT = re.compile(
    r"(?:application (?:to|with)|apply(?:ing)? to|interest in .+? at|"
    r"opportunity (?:at|with)|position at|role at)\s+"
    r"([A-Z][\w&.\- ]{1,40}?)(?:\s*[|,!]|\s*$)",
)


def extract_company_from_email(from_header: str, subject: str) -> str:
    """Extracts likely company name from sender or subject."""
    domain_match = re.search(r"@([\w\-]+)\.", from_header or "")
    if domain_match:
        domain = domain_match.group(1).lower()
        full = _sender_domain(from_header)
        if domain not in CONSUMER_DOMAINS and (
            not _is_ats_domain(full) or _is_employer_ats(full)
        ):
            return domain.capitalize()

        # Sender is pure ATS infrastructure, so the employer -- if it is
        # anywhere -- is named in the subject.
        in_subject = COMPANY_IN_SUBJECT.search(_normalize_text(subject or ""))
        if in_subject:
            return in_subject.group(1).strip()

    subj_match = re.search(
        r"(?:at|with|to)\s+([A-Z][A-Za-z0-9\s]+?)(?:[\-–:,]|$)", subject or ""
    )
    if subj_match:
        return subj_match.group(1).strip()

    return "Unknown Company"


def _decode(raw: Optional[str]) -> str:
    """Decodes an RFC 2047 header ("=?utf-8?q?...?=") to plain text.

    Recruiter mail is full of encoded subjects; without this the intent
    regexes match against mojibake and quietly classify everything as
    'unknown'.
    """
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return raw


def _body_text(message: email.message.Message, max_chars: int = 4000) -> str:
    """Best-effort plain-text body.

    Prefers text/plain; falls back to text/html with tags stripped, since
    plenty of ATS mail is HTML-only and skipping it would blind the
    classifier to exactly the messages we care about. Truncated because
    the intent signal is always near the top and full bodies are large.
    """
    parts: List[str] = []
    html_parts: List[str] = []

    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_filename():  # skip attachments
            continue
        try:
            payload = part.get_payload(decode=True)
        except Exception:
            continue
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        try:
            text = payload.decode(charset, errors="replace")
        except (LookupError, UnicodeDecodeError):
            text = payload.decode("utf-8", errors="replace")

        if part.get_content_type() == "text/plain":
            parts.append(text)
        elif part.get_content_type() == "text/html":
            html_parts.append(text)

    if not parts and html_parts:
        stripped = re.sub(r"(?is)<(script|style).*?</\1>", " ", "\n".join(html_parts))
        stripped = re.sub(r"(?s)<[^>]+>", " ", stripped)
        parts = [re.sub(r"\s+", " ", stripped)]

    return "\n".join(parts)[:max_chars]


def connect(
    address: Optional[str] = None,
    password: Optional[str] = None,
    host: Optional[str] = None,
    profile: Optional[str] = None,
) -> imaplib.IMAP4_SSL:
    """Opens an authenticated IMAP4_SSL connection for the active profile.

    Raises RuntimeError with an actionable message when credentials are
    absent, rather than surfacing imaplib's opaque authentication error.
    """
    load_dotenv(profile_paths.env_path(profile))

    address = address or os.environ.get("GMAIL_ADDRESS")
    password = password or os.environ.get("GMAIL_APP_PASSWORD")
    host = host or os.environ.get("IMAP_HOST") or DEFAULT_IMAP_HOST

    if not address or not password:
        raise RuntimeError(
            "No mailbox credentials. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to "
            f"{profile_paths.env_path(profile)} (the app password comes from "
            "https://myaccount.google.com/apppasswords and needs 2-Step "
            "Verification enabled)."
        )

    conn = imaplib.IMAP4_SSL(host)
    try:
        conn.login(address, password)
    except imaplib.IMAP4.error as exc:
        raise RuntimeError(
            f"Mailbox login failed for {address}: {exc}. Gmail rejects a normal "
            "account password here -- GMAIL_APP_PASSWORD must be a 16-character "
            "app password."
        ) from exc
    return conn


def fetch_recent_messages(
    conn: imaplib.IMAP4_SSL,
    days: int = 30,
    folder: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, str]]:
    """Returns recent messages as {from, subject, body, date} dicts.

    Filters server-side with IMAP SINCE so a large mailbox does not get
    pulled down in full.
    """
    folder = folder or os.environ.get("IMAP_FOLDER") or DEFAULT_FOLDER
    status, _ = conn.select(folder, readonly=True)
    if status != "OK":
        raise RuntimeError(f"Could not open mailbox folder {folder!r}.")

    since = (datetime.now() - timedelta(days=days)).strftime("%d-%b-%Y")
    status, data = conn.search(None, "SINCE", since)
    if status != "OK":
        return []

    ids = data[0].split()
    if limit:
        ids = ids[-limit:]  # newest N

    messages: List[Dict[str, str]] = []
    for msg_id in reversed(ids):
        # Gmail intermittently answers a single FETCH with "System Error",
        # which imaplib raises as IMAP4.abort and which kills the whole
        # scan if it escapes. One unreadable message is not worth losing
        # the run over, so skip it; abort also invalidates the connection,
        # so stop reading this folder and let the caller reconnect.
        try:
            status, payload = conn.fetch(msg_id, "(RFC822)")
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error:
            continue

        if status != "OK" or not payload or not isinstance(payload[0], tuple):
            continue

        try:
            parsed = email.message_from_bytes(payload[0][1])
        except Exception:
            continue
        messages.append(
            {
                "from": _decode(parsed.get("From")),
                "subject": _decode(parsed.get("Subject")),
                "date": _decode(parsed.get("Date")),
                "body": _body_text(parsed),
            }
        )
    return messages


def _normalize_company(name: str) -> str:
    """Folds a company name for comparison: lowercase, no punctuation, no
    Inc/LLC/Corp suffix. 'Rula, Inc.' and 'rula' must match."""
    cleaned = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    cleaned = re.sub(
        r"\b(inc|llc|ltd|corp|corporation|co|company|group|holdings)\b", " ", cleaned
    )
    return " ".join(cleaned.split())


def match_company_to_jobs(
    company: str, jobs: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Returns the job rows whose company plausibly matches `company`.

    Deliberately conservative: exact normalized equality, or one name
    fully containing the other as a whole token run. Loose fuzzy matching
    here would attach a rejection email to the wrong application.
    """
    target = _normalize_company(company)
    if not target or target == "unknown company":
        return []

    matches = []
    for job in jobs:
        candidate = _normalize_company(job.get("company", ""))
        if not candidate:
            continue
        if candidate == target or (
            len(target) >= 4
            and len(candidate) >= 4
            and (target in candidate or candidate in target)
        ):
            matches.append(job)
    return matches


def process_email_messages(
    messages: List[Dict[str, str]],
    conn: Optional[Any] = None,
    jobs: Optional[List[Dict[str, Any]]] = None,
    trust_all: bool = False,
) -> List[Dict[str, Any]]:
    """Returns one result per JOB-APPLICATION message.

    With trust_all, the gate is skipped -- used for Gmail label folders,
    where the user has already classified the mail by hand.

    Otherwise messages that do not pass is_job_application_mail() are
    dropped entirely rather than reported as 'unknown'. On a real mailbox the
    overwhelming majority of mail is neither, and reporting it buried the
    handful of genuine results in newsletter noise.

    Writes nothing. `jobs` is the candidate list to match against; when
    omitted no matching is attempted, which keeps the pure-classification
    path usable without a database.
    """
    known_companies = {
        _normalize_company(job.get("company", "")) for job in (jobs or [])
    }
    known_companies.discard("")

    results = []
    for msg in messages:
        subject = msg.get("subject", "")
        body = msg.get("body", "")
        from_hdr = msg.get("from", "")

        if not trust_all and not is_job_application_mail(
            from_hdr, subject, body, known_companies=known_companies
        ):
            continue

        intent = classify_email_intent(subject, body, from_hdr)
        company = extract_company_from_email(from_hdr, subject)
        matches = match_company_to_jobs(company, jobs) if jobs else []

        results.append(
            {
                "from": from_hdr,
                "company": company,
                "subject": subject,
                "date": msg.get("date", ""),
                "intent": intent,
                "matched_jobs": [
                    {
                        "id": m.get("id"),
                        "title": m.get("title"),
                        "status": m.get("status"),
                    }
                    for m in matches
                ],
            }
        )
    return results


# --- Sent mail -------------------------------------------------------
#
# The inbox only shows what came back. The sent folder shows what went
# out, which answers a question nothing else here can: which applications
# got no reply at all. A silent application looks identical to one never
# submitted unless the outbound side is read.

SENT_FOLDER = "[Gmail]/Sent Mail"

SENT_APPLICATION = re.compile(
    r"(applying (for|to)|application for|applied (to|for)|"
    r"submitted my application|resume attached|cv attached|"
    r"cover letter|please find my resume|my application for)",
    re.I,
)

SENT_FOLLOWUP = re.compile(
    r"(following up|follow(ing)? up on|checking (on|in)|"
    r"status of my application|update on my application|"
    r"where things stand|any update|next steps|"
    r"haven'?t (heard|received))",
    re.I,
)

SENT_OUTREACH = re.compile(
    r"(wanted to reach out|reaching out|introduce myself|introducing myself|"
    r"would love to connect|putting a real person|reach out directly)",
    re.I,
)


# Unambiguous application language, used to hold consumer-domain
# recipients to a higher bar (see scan_sent). "following up" and
# "reaching out" are ordinary English between friends; "resume attached"
# is not.
SENT_STRICT = re.compile(
    r"(applied (to|for)|applying (for|to)|my application (for|to)|"
    r"resume attached|attached (is |my )?(resume|cv)|cover letter|"
    r"submitted my application|status of my application)",
    re.I,
)


def classify_sent_intent(subject: str, body: str) -> str:
    """'application', 'follow_up', 'outreach', or 'unknown'.

    Follow-up is tested before application because a follow-up almost
    always restates the application it is chasing ("checking on the status
    of my application for X"), and the chase is the newer fact.
    """
    text = _normalize_text(f"{subject} {body}")
    if SENT_FOLLOWUP.search(text):
        return "follow_up"
    if SENT_APPLICATION.search(text):
        return "application"
    if SENT_OUTREACH.search(text):
        return "outreach"
    return "unknown"


def gmail_search(conn: imaplib.IMAP4_SSL, query: str) -> List[bytes]:
    """Runs a raw Gmail search over IMAP and returns matching message ids.

    Gmail's X-GM-RAW takes the same syntax as the search box, but imaplib
    splits arguments on whitespace, so any multi-term query has to be sent
    as an IMAP literal rather than as a plain argument -- passing it
    directly fails with "Could not parse command".
    """
    conn.literal = query.encode("utf-8")
    status, data = conn.search("UTF-8", "X-GM-RAW")
    if status != "OK" or not data or not data[0]:
        return []
    return data[0].split()


def scan_sent(
    conn: imaplib.IMAP4_SSL,
    days: int = 365,
    limit: Optional[int] = 200,
) -> List[Dict[str, Any]]:
    """Job-related mail this user SENT, newest first.

    Narrowed server-side with a Gmail query rather than by walking the
    whole folder, which would mean fetching thousands of personal emails
    to find a few dozen.
    """
    status, _ = conn.select(f'"{SENT_FOLDER}"', readonly=True)
    if status != "OK":
        return []

    since = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = (
        f"after:{since} ("
        '"applying for" OR "application for" OR "applied to" OR '
        '"submitted my application" OR "resume attached" OR "cover letter" OR '
        '"following up" OR "status of my application" OR "next steps" OR '
        '"wanted to reach out" OR "reaching out"'
        ")"
    )

    ids = gmail_search(conn, query)
    if limit:
        ids = ids[-limit:]

    results = []
    for msg_id in reversed(ids):
        try:
            status, payload = conn.fetch(msg_id, "(RFC822)")
        except imaplib.IMAP4.abort:
            raise
        except imaplib.IMAP4.error:
            continue
        if status != "OK" or not payload or not isinstance(payload[0], tuple):
            continue
        try:
            parsed = email.message_from_bytes(payload[0][1])
        except Exception:
            continue

        subject = _decode(parsed.get("Subject"))
        body = _body_text(parsed)
        recipient = _decode(parsed.get("To"))

        # The server-side query is deliberately broad -- it is a net, not
        # a verdict. "reaching out" and "following up" are ordinary
        # English, so a school transport inquiry and a personal thread
        # both matched it. Two local filters do the actual judging.
        if _is_non_job_domain(_sender_domain(recipient)):
            continue
        if NON_JOB_CONTEXT.search(_normalize_text(f"{subject} {body}")[:2000]):
            continue

        intent = classify_sent_intent(subject, body)
        if intent == "unknown":
            continue

        # Mail to a personal address has to say something unmistakably
        # about an application. Job correspondence goes to company
        # domains; a thread with a friend that happens to say "following
        # up" does not become a job application. This is what was
        # promoting "Re: Survive The Apocalypse" into the report.
        domain = _sender_domain(recipient)
        root = domain.split(".")[0] if domain else ""
        if root in CONSUMER_DOMAINS and not SENT_STRICT.search(
            _normalize_text(f"{subject} {body}")
        ):
            continue

        results.append(
            {
                "to": recipient,
                "domain": _sender_domain(recipient),
                "subject": subject,
                "date": _decode(parsed.get("Date")),
                "intent": intent,
            }
        )
    return results


def applications_without_replies(
    sent: List[Dict[str, Any]], received: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Outbound applications with no inbound mail from the same domain.

    This is the signal the inbox alone cannot produce: a silent rejection
    is indistinguishable from an application that was never sent.

    Only as trustworthy as the `received` list handed in. Scanning 45 days
    of inbox against two years of sent mail will report old applications
    as unanswered when the reply simply predates the window, so pass a
    `received` set covering at least the same period as `sent`.
    """
    replied = {
        _sender_domain(r.get("from", "")).lower() for r in received if r.get("from")
    }
    replied.discard("")

    silent = []
    for item in sent:
        if item["intent"] not in ("application", "follow_up"):
            continue
        domain = (item.get("domain") or "").lower()
        if domain and domain not in replied:
            silent.append(item)
    return silent


def _parse_message_date(date_str: Optional[str]) -> Optional[datetime]:
    """Safely parse RFC 2822 or ISO date string into a timezone-aware datetime."""
    if not date_str:
        return None
    try:
        parsed_tuple = email.utils.parsedate_tz(date_str)
        if parsed_tuple:
            timestamp = email.utils.mktime_tz(parsed_tuple)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except Exception:
        pass
    try:
        iso_str = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def rank_silent_applications(
    silent: List[Dict[str, Any]], now: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Ages, tiers, and ranks unanswered applications.

    Tiers:
      - 'follow_up': 8 to 21 days waiting (ideal window for a polite follow-up)
      - 'warm': 0 to 7 days waiting (standard recruiter response window)
      - 'stale': 22+ days waiting (likely silent rejection or closed req)

    Returns a sorted list of application dicts enriched with:
      - 'days_waiting': int (default 0 if date unknown)
      - 'tier': 'follow_up' | 'warm' | 'stale'
      - 'tier_label': str
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    ranked = []
    for item in silent:
        entry = dict(item)
        dt = _parse_message_date(item.get("date"))
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = max(0, (now - dt).days)
        else:
            days = 0

        entry["days_waiting"] = days
        if days <= 7:
            entry["tier"] = "warm"
            entry["tier_label"] = "Warm (0-7d)"
        elif days <= 21:
            entry["tier"] = "follow_up"
            entry["tier_label"] = "Follow-Up Recommended (8-21d)"
        else:
            entry["tier"] = "stale"
            entry["tier_label"] = "Stale (22d+)"

        ranked.append(entry)

    # Priority sort order: follow_up (urgent action) first by days desc, then warm by days desc, then stale
    tier_weights = {"follow_up": 0, "warm": 1, "stale": 2}
    ranked.sort(key=lambda x: (tier_weights.get(x["tier"], 3), -x["days_waiting"]))
    return ranked


def generate_follow_up_draft(
    item: Dict[str, Any], candidate_name: Optional[str] = None
) -> Dict[str, str]:
    """Generates a concise, polite follow-up email subject and body for a silent application."""
    if not candidate_name:
        try:
            profile_data = profile_paths.load_profile()
            candidate_name = profile_data.get("name") or "Candidate"
        except Exception:
            candidate_name = "Candidate"

    subject_raw = item.get("subject", "")
    clean_sub = re.sub(
        r"^(Re:\s*|Fwd:\s*)+", "", subject_raw, flags=re.IGNORECASE
    ).strip()
    if not clean_sub:
        clean_sub = f"Application ({item.get('domain', 'Role')})"

    follow_up_subject = f"Following up: {clean_sub}"

    body = (
        f"Hi Team,\n\n"
        f"I wanted to follow up on my application ({clean_sub}). "
        f"I remain very enthusiastic about the team's mission and would welcome the chance to discuss how my background aligns with the role.\n\n"
        f"Please let me know if there are any additional materials or information I can provide.\n\n"
        f"Best regards,\n"
        f"{candidate_name}"
    )

    return {
        "to": item.get("to", ""),
        "domain": item.get("domain", ""),
        "subject": follow_up_subject,
        "body": body,
    }


def _load_jobs(profile: Optional[str] = None) -> List[Dict[str, Any]]:
    """All job rows for this profile, as plain dicts for matching."""
    try:
        connection = db.get_db(profile)
    except Exception:
        return []
    try:
        rows = connection.execute(
            "SELECT id, title, company, status FROM jobs"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def list_folders(conn: imaplib.IMAP4_SSL) -> List[str]:
    """Every folder (Gmail label) on the account."""
    status, raw = conn.list()
    if status != "OK":
        return []
    names = []
    for line in raw or []:
        decoded = (
            line.decode(errors="replace") if isinstance(line, bytes) else str(line)
        )
        if '"' in decoded:
            names.append(decoded.rsplit('"', 2)[-2])
    return names


def sync_inbox(
    days: int = 30,
    limit: Optional[int] = None,
    folder: Optional[str] = None,
    profile: Optional[str] = None,
    include_labels: bool = True,
) -> List[Dict[str, Any]]:
    """Connects, fetches, classifies, and matches. Returns the results.

    Scans the inbox through the gate, then adds any Gmail job labels
    the account actually has, trusting those outright.
    """
    connection = connect(profile=profile)
    jobs = _load_jobs(profile)
    results: List[Dict[str, Any]] = []
    seen = set()

    def _collect(name, trusted, since_days):
        nonlocal connection
        try:
            messages = fetch_recent_messages(
                connection, days=since_days, folder=name, limit=limit
            )
        except imaplib.IMAP4.abort as exc:
            # The connection is unusable after an abort. Reconnect once and
            # move on rather than losing every folder after the bad one.
            cli_art.cli_warning(f"Mailbox dropped while reading {name}: {exc}")
            try:
                connection = connect(profile=profile)
            except Exception:
                return
            return
        for result in process_email_messages(messages, jobs=jobs, trust_all=trusted):
            key = (result["from"], result["subject"], result["date"])
            if key in seen:
                continue
            seen.add(key)
            result["source"] = name
            results.append(result)

    try:
        _collect(folder or DEFAULT_FOLDER, False, days)

        if include_labels:
            available = set(list_folders(connection))
            for label in JOB_LABEL_FOLDERS:
                if label not in available:
                    continue
                try:
                    # Labels are a curated archive, so they are worth
                    # reading further back than the inbox sweep.
                    _collect(f'"{label}"', True, max(days, 3650))
                except Exception as exc:  # a label can vanish mid-run
                    cli_art.cli_warning(f"Skipped label {label!r}: {exc}")
    finally:
        try:
            connection.logout()
        except Exception:
            pass

    return results


def _render(results: List[Dict[str, Any]], show_all: bool = False) -> None:
    interesting = [r for r in results if r["intent"] != "unknown"]
    shown = results if show_all else interesting

    counts: Dict[str, int] = {}
    for r in results:
        counts[r["intent"]] = counts.get(r["intent"], 0) + 1

    cli_art.print_literal(
        f"\n  Scanned {len(results)} messages: "
        + ", ".join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
        + "\n"
    )

    for r in shown:
        matched = r["matched_jobs"]
        tag = f"[{r['intent']}]"
        source = r.get("source", "")
        origin = "" if source in ("", "INBOX") else f"  [{source.strip(chr(34))}]"
        line = f"  {tag:<17} {r['company']:<22} {r['subject'][:48]}{origin}"
        cli_art.print_literal(line)
        for m in matched:
            cli_art.print_literal(
                f"      -> matches job: {m['title']} (status: {m['status']})"
            )
        if not matched and r["intent"] in ("interview", "offer", "rejection"):
            cli_art.print_literal("      -> no matching job in the database")

    if not show_all and len(results) != len(interesting):
        cli_art.print_literal(
            f"\n  ({len(results) - len(interesting)} unclassified messages hidden; "
            "pass --all to see them.)"
        )


def _render_matches(results: List[Dict[str, Any]], apply_changes: bool) -> None:
    """Match classified mail to saved roles and report proposed changes."""
    import email_matcher
    import picker

    rows = picker.list_all_evaluated_jds()
    jobs = [
        {
            "path": r["path"],
            "title": r["title"],
            "company": r["company"],
            "application": r.get("application"),
        }
        for r in rows
    ]

    proposals = email_matcher.plan_updates(results, jobs)
    if not proposals:
        cli_art.print_literal(
            f"\n  No status changes proposed. "
            f"({len(jobs)} saved roles; nothing matched confidently.)\n"
        )
        return

    cli_art.print_literal(f"\n  Proposed status changes ({len(proposals)}):\n")
    for p in proposals:
        cli_art.print_literal(
            f"  [{p['action']}] {p['confidence']:.2f}  {p['company'][:18]:<18} "
            f"{(p['job_title'] or '')[:30]:<30} {p['current_status'] or '-'} -> "
            f"{p['new_status']}"
        )
        cli_art.print_literal(f"        {'; '.join(p['reasons'])[:96]}")

    if not apply_changes:
        cli_art.print_literal(
            "\n  Nothing written -- pass --apply to write the [auto] ones.\n"
        )
        return

    applied = email_matcher.apply_updates(proposals)
    skipped = len(proposals) - applied
    cli_art.print_literal(
        f"\n  Wrote {applied} status change(s) to JD files and SQLite application_log. "
        f"{skipped} left for review (below the auto-apply threshold).\n"
    )


def _render_sent(received: List[Dict[str, Any]], days: int, profile) -> None:
    """Sent-side report. Opens its own connection so the inbox scan above
    has already released the first one."""
    try:
        connection = connect(profile=profile)
    except RuntimeError as exc:
        cli_art.display_error(str(exc))
        return

    try:
        sent = scan_sent(connection, days=max(days, 365))
    finally:
        try:
            connection.logout()
        except Exception:
            pass

    counts: Dict[str, int] = {}
    for item in sent:
        counts[item["intent"]] = counts.get(item["intent"], 0) + 1

    cli_art.print_literal(
        f"\n  Sent mail: {len(sent)} job-related messages -- "
        + ", ".join(f"{v} {k}" for k, v in sorted(counts.items(), key=lambda x: -x[1]))
        + "\n"
    )
    for item in sent[:20]:
        cli_art.print_literal(
            f"  {'[' + item['intent'] + ']':<14} {item['domain'][:24]:<24} "
            f"{item['subject'][:44]}"
        )

    silent = applications_without_replies(sent, received)
    if silent:
        ranked = rank_silent_applications(silent)
        cli_art.print_literal(
            f"\n  {len(silent)} application(s) with no reply from that domain "
            f"in the last {days} days of inbox:"
        )
        for item in ranked[:12]:
            tier_badge = f"[{item['tier'].upper()}]"
            cli_art.print_literal(
                f"      {item['domain'][:22]:<22} {tier_badge:<14} {item['days_waiting']:>2}d waiting   {item['subject'][:34]}"
            )
        cli_art.print_literal(
            "      (use `resume inbox-sync --chase` or `--sent --chase` to view follow-up email drafts)"
        )


def _render_chase_list(
    silent: List[Dict[str, Any]],
    draft_top_n: int = 3,
    candidate_name: Optional[str] = None,
) -> None:
    """Renders actionable chase list with tiered aging and ready-to-use email drafts."""
    ranked = rank_silent_applications(silent)
    if not ranked:
        cli_art.cli_info("No silent applications found in the scanned window.")
        return

    cli_art.print_literal("\n  " + "=" * 64)
    cli_art.print_literal("  CHASE LIST (Silence Detector & Follow-Up Action)")
    cli_art.print_literal("  " + "=" * 64)

    follow_ups = [item for item in ranked if item["tier"] == "follow_up"]
    warms = [item for item in ranked if item["tier"] == "warm"]
    stales = [item for item in ranked if item["tier"] == "stale"]

    cli_art.print_literal(
        f"\n  Breakdown: {len(follow_ups)} action recommended, {len(warms)} warm (0-7d), {len(stales)} stale (22d+)."
    )

    if follow_ups:
        cli_art.print_literal("\n  [Action Recommended: 8-21 Days Waiting]")
        for item in follow_ups:
            cli_art.print_literal(
                f"    • {item['domain'][:24]:<24} ({item['days_waiting']} days)  {item['subject'][:40]}"
            )

    if warms:
        cli_art.print_literal("\n  [Warm / Recent: 0-7 Days Waiting]")
        for item in warms:
            cli_art.print_literal(
                f"    • {item['domain'][:24]:<24} ({item['days_waiting']} days)  {item['subject'][:40]}"
            )

    if stales:
        cli_art.print_literal("\n  [Stale / Likely Closed: 22+ Days Waiting]")
        for item in stales[:5]:
            cli_art.print_literal(
                f"    • {item['domain'][:24]:<24} ({item['days_waiting']} days)  {item['subject'][:40]}"
            )

    candidates_to_draft = (
        follow_ups[:draft_top_n] if follow_ups else (warms[:1] if warms else stales[:1])
    )
    if candidates_to_draft:
        cli_art.print_literal("\n  " + "-" * 64)
        cli_art.print_literal("  DRAFT FOLLOW-UP EMAILS")
        cli_art.print_literal("  " + "-" * 64)
        for draft_item in candidates_to_draft:
            draft = generate_follow_up_draft(draft_item, candidate_name=candidate_name)
            cli_art.print_literal(f"\n  To: {draft['to'] or draft['domain']}")
            cli_art.print_literal(f"  Subject: {draft['subject']}")
            cli_art.print_literal("  Body:")
            for line in draft["body"].split("\n"):
                cli_art.print_literal(f"    {line}")
            cli_art.print_literal("  " + "-" * 64)


def main(argv: Optional[List[str]] = None) -> int:
    """CLI execution entrypoint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days", type=int, default=30, help="how far back to scan (default 30)"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="only the newest N messages"
    )
    parser.add_argument("--folder", default=None, help="mailbox folder (default INBOX)")
    parser.add_argument(
        "--all", action="store_true", help="also show unclassified messages"
    )
    parser.add_argument(
        "--no-labels",
        action="store_true",
        help="skip the Gmail job labels and scan only the inbox",
    )
    parser.add_argument(
        "--sent",
        action="store_true",
        help="also analyse sent mail (applications, follow-ups, and which got no reply)",
    )
    parser.add_argument(
        "--chase",
        action="store_true",
        help="display aged chase list with drafted follow-up emails for unanswered applications",
    )
    parser.add_argument(
        "--match",
        action="store_true",
        help="match classified mail to saved roles and show proposed status changes",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the high-confidence status changes (implies --match)",
    )
    args = parser.parse_args(argv)

    cli_art.print_literal("")
    cli_art.cli_info(f"Scanning the last {args.days} days of mail...")

    try:
        results = sync_inbox(
            days=args.days,
            limit=args.limit,
            folder=args.folder,
            include_labels=not args.no_labels,
        )
    except RuntimeError as exc:
        cli_art.display_error(str(exc))
        return 1

    _render(results, show_all=args.all)

    if args.match or args.apply:
        _render_matches(results, apply_changes=args.apply)

    if args.sent or args.chase:
        _render_sent(results, days=args.days, profile=None)

    if args.chase:
        password = _get_password()
        if password:
            sent = scan_sent_mail(
                days=args.days,
                user=os.environ.get("GMAIL_USER"),
                password=password,
                limit=args.limit,
            )
            silent = applications_without_replies(sent, results)
            _render_chase_list(silent)

    if not args.apply:
        cli_art.print_literal(
            "\n  This is a read-only report -- no application statuses were changed.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
