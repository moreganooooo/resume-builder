"""Show what the claims ledger flags using a fictional job and applicant."""

import claims_ledger


def main() -> None:
    """Run the same rule check that the resume validator uses."""
    requirement = "Own contract renewals for existing customers."
    supported_bullet = "Ran email retention campaigns."
    unsupported_bullet = "Owned contract renewals."
    ledger = claims_ledger.load(
        {
            "claims_ledger": {
                "banned_topics": [
                    {
                        "name": "contract renewals",
                        "pattern": r"\brenewals?\b",
                        "instead": "retention campaigns",
                    }
                ]
            }
        }
    )

    print(f"Job asks for: {requirement}")
    print(f"Applicant's verified experience: {supported_bullet}")
    for topic, _ in claims_ledger.unsupported_asks(requirement, ledger):
        print(f"Experience gap: {topic}")

    for bullet in (unsupported_bullet, supported_bullet):
        draft = {"EXPERIENCE": [{"company": "Example Co", "achievements": [bullet]}]}
        findings = claims_ledger.check_resume(draft, ledger)
        print(f"\nDraft: {bullet}")
        if findings:
            for finding in findings:
                print(f"  Flagged: {finding}")
        else:
            print("  No configured claims flagged.")


if __name__ == "__main__":
    main()
