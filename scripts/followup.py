"""
followup.py — cadence classification for the follow-up tracker: given an
application's status and dates (see jd_manager.save_application_status()/
read_application_status()), decides whether it's overdue for a follow-up,
still within a reasonable waiting window, or cold (enough follow-ups sent
with no response that chasing further isn't worth it).

Pure date math, ported from career-ops's followup-cadence.mjs -- no LLM
call, no network access. Thresholds match the original exactly.
"""

import datetime

CADENCE = {
    "applied_first": 7,
    "applied_subsequent": 7,
    "applied_max_followups": 2,
    "responded_subsequent": 3,
    "interview_thankyou": 1,
}


def compute_urgency(application: dict | None) -> str | None:
    """Returns "overdue", "waiting", "cold", or None (no application
    status recorded yet, or a terminal status -- Offer/Rejected/Withdrawn
    -- that a follow-up cadence doesn't apply to). application is the
    dict jd_manager.read_application_status() returns."""
    if not application:
        return None
    status = application.get("status")
    if status not in ("Applied", "Responded", "Interview"):
        return None

    anchor = application.get("status_changed_at")
    if not anchor:
        return None
    try:
        days_since_status_change = (
            datetime.datetime.now() - datetime.datetime.fromisoformat(anchor)
        ).days
    except ValueError:
        return None

    follow_up_count = application.get("follow_up_count", 0) or 0
    last_followup_at = application.get("last_followup_at")
    days_since_last_followup = None
    if last_followup_at:
        try:
            days_since_last_followup = (
                datetime.datetime.now()
                - datetime.datetime.fromisoformat(last_followup_at)
            ).days
        except ValueError:
            days_since_last_followup = None

    if status == "Applied":
        if follow_up_count >= CADENCE["applied_max_followups"]:
            return "cold"
        if (
            follow_up_count == 0
            and days_since_status_change >= CADENCE["applied_first"]
        ):
            return "overdue"
        if (
            follow_up_count > 0
            and days_since_last_followup is not None
            and days_since_last_followup >= CADENCE["applied_subsequent"]
        ):
            return "overdue"
        return "waiting"

    if status == "Responded":
        return (
            "overdue"
            if days_since_status_change >= CADENCE["responded_subsequent"]
            else "waiting"
        )

    if status == "Interview":
        return (
            "overdue"
            if days_since_status_change >= CADENCE["interview_thankyou"]
            else "waiting"
        )

    return None
