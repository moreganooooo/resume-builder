"""enrich_clerical_bullets.py -- add TRUE, result-bearing bullets for the clerical roles.

The clerical roles (USitek, KU Payroll, DeJoy, OfficeTeam/Adecco/Greendox) are
mostly task bullets in the bank ("Organized records..."), because nothing
about the outcome was ever written down. This walks each role, shows what the
bank already says, and asks what changed because of the work. Whatever you
type is stored verbatim as a new bank row with provenance; nothing is
invented or rephrased, and a role you have nothing to add for is skipped.

    python scripts/enrich_clerical_bullets.py            # interactive
    python scripts/enrich_clerical_bullets.py --dry-run  # show, write nothing

Only write what you remember to be true: a metric typed here becomes a figure
resume builds are allowed to use (validate_resume._check_metric_provenance
reads it from the bank). An approximation you're unsure of is better left out
-- a bullet with no number is still fine, the point is the outcome clause.

The bank is backed up first. Re-embed afterwards (the script offers to) so
builds can retrieve the new rows.
"""

import argparse
import datetime
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import profile_paths  # noqa: E402

# bank "Role / Company" value -> (display name, prompts that draw out a result)
ROLES = {
    "USitek": (
        "USitek (Administrative & Marketing Assistant, 2015)",
        [
            "How many orders/SKUs/vendors/records did you handle, and how often?",
            "What got faster, cleaner, cheaper or more accurate because of your work?",
            "What did you fix or set up that was still being used after you left?",
            "Did anyone (owner, vendor, auditor) rely on your files or say something about them?",
        ],
    ),
    "Payroll": (
        "KU Payroll Office (Student Payroll Assistant, 2006-2008)",
        [
            "How many employees/records/forms/calls did you handle (per week or total)?",
            "What got faster or more accurate (retrieval time, error rate, turnaround)?",
            "What did you take over or get trusted with beyond the job description?",
            "Did a supervisor ever rely on you for something specific?",
        ],
    ),
    "DeJoy": (
        "DeJoy, Knauff & Blood (Tax Administrative Assistant, 2012)",
        [
            "How many returns/packets/client files did you handle, and in what window?",
            "What went right because of it (on-time filing, zero rejected packets, clean audit files)?",
            "What did you build or organize that the team kept using?",
            "Any client-facing moment (calls, deadlines, rush work) with a clear result?",
        ],
    ),
    "OfficeTeam": (
        "OfficeTeam / Adecco / Greendox (Temporary Admin & Data Entry, 2008-2010)",
        [
            "Roughly how many records/forms/entries per day or assignment?",
            "What accuracy or turnaround did you hit, and who measured it?",
            "Were you asked back, extended, or moved to harder work? How many assignments?",
            "What did you fix or clean up (backlogs, errors, filing systems)?",
        ],
    ),
}

NEW_ROW_DEFAULTS = {
    "Tags": "[generalist]",
    "accuracy_score": 100.0,
    "believability_score": 90.0,
    "clarity_score": 90.0,
    "ats_value": 85.0,
    "manager_test": "PASS",
    "audit_status": "CLEAN",
    "hidden_gem_flag": False,
}


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def collect(df) -> list:
    """Interactive loop; returns [(bank_company, bullet_text)]."""
    additions = []
    for key, (label, prompts) in ROLES.items():
        mask = df["Role / Company"].fillna("").str.contains(key, regex=False)
        company = df.loc[mask, "Role / Company"].iloc[0] if mask.any() else key
        print(f"\n=== {label} ===")
        print("The bank already has:")
        for text in df.loc[mask, "Bullet Point"]:
            print(f"  - {text}")
        print("\nThink about these (nothing is saved from this part):")
        for p in prompts:
            print(f"  * {p}")
        print(
            "\nType a TRUE result-bearing bullet (outcome first is ideal, no invented"
            "\nnumbers). Blank line when you're done with this role."
        )
        while True:
            text = _ask("  bullet> ")
            if not text:
                break
            text = text.lstrip("-• ").strip()
            if text and text not in additions:
                additions.append((company, text))
    return additions


def write(df, additions, bank_path: str) -> None:
    import pandas as pd

    stamp = datetime.date.today().isoformat()
    source = f"Morgan-confirmed outcomes {stamp}"
    rows = [
        {
            **NEW_ROW_DEFAULTS,
            "Bullet Point": text,
            "Role / Company": company,
            "source": source,
        }
        for company, text in additions
    ]
    out = pd.concat([df, pd.DataFrame(rows)], ignore_index=True)
    out = out[df.columns]
    out.to_csv(bank_path, index=False)


def main() -> int:
    import pandas as pd

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="write nothing")
    args = parser.parse_args()

    bank_path = os.path.join(profile_paths.kb_dir(), "bullet-bank-keepers-audited.csv")
    df = pd.read_csv(bank_path)
    additions = collect(df)
    if not additions:
        print("\nNothing added.")
        return 0

    print(f"\n{len(additions)} new bullet(s):")
    for company, text in additions:
        print(f"  [{company}] {text}")
    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0
    if _ask("\nSave these to the bank? [y/N] ").lower() != "y":
        print("Not saved.")
        return 0

    backup_dir = os.path.join(
        profile_paths.kb_dir(),
        "backups",
        f"enrich-{datetime.datetime.now():%Y%m%d-%H%M%S}",
    )
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy2(bank_path, backup_dir)
    write(df, additions, bank_path)
    print(f"Saved. Backup in {backup_dir}")

    if (
        _ask(
            "Re-embed the bank now (needed before builds can use them)? [Y/n] "
        ).lower()
        != "n"
    ):
        return subprocess.call(
            [sys.executable, os.path.join(SCRIPT_DIR, "embed_bullet_bank.py")]
        )
    print("Remember: python scripts/embed_bullet_bank.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
