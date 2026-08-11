import os
import json
import sys
import time
import pandas as pd
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
import profile_paths
load_dotenv(profile_paths.env_path())

# Import shared objects from orchestrator
from orchestrator import CritiqueSchema, GeminiClient, ResumeEngine
import cli_art
import theme

SLEEP = 8  # seconds between calls — generous since this is a one-time offline task

engine = ResumeEngine()
critique_prompt = engine.load_prompt("critique_bullet.md")
manager_test_rules = json.dumps(engine.load_yaml(engine.scoring_dir, "manager_test.yaml"))
believability_rules = json.dumps(engine.load_yaml(engine.scoring_dir, "believability.yaml"))
# redundancy_rules (own_employer_name / unneeded_calendar_dates) from
# style_rules.yaml -- this is the FIRST scoring gate a bullet ever passes
# through (straight out of bootstrap extraction, before any rewrite), so
# without this a bullet that already restates its own employer name in
# its raw extracted text would score fine and never get flagged.
redundancy_rules = json.dumps(engine.load_yaml(engine.rules_dir, "style_rules.yaml").get("redundancy_rules", {}))

critique_system = (
    f"\n\n{critique_prompt}"
    f"\n\nRULES:\n{manager_test_rules}"
    f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
    f"\n\nREDUNDANCY RULES (the bullet's own Role/Company is provided in the input -- "
    f"flag it if the bullet's text restates that SAME company's name, or includes an "
    f"unneeded specific calendar month/season + year):\n{redundancy_rules}"
)

csv_path = os.path.join(engine.kb_dir, "bullet-bank-clean.csv")
df = pd.read_csv(csv_path)

out_path = os.path.join(engine.kb_dir, "bullet-bank-audited.csv")

# Column name candidates for the bullet text field (handles variations across files)
BULLET_COL_CANDIDATES = ["bullet", "achievement", "Bullet Point"]

def detect_bullet_col(columns):
    """Return the first matching bullet column name, or None if not found."""
    for c in BULLET_COL_CANDIDATES:
        if c in columns:
            return c
    return None

# --- RESUME FROM CHECKPOINT ---
# If a partial output file already exists, load already-scored bullets and
# skip them so a restart picks up exactly where it left off.
already_scored_bullets = set()
results = []

if os.path.exists(out_path):
    try:
        existing = pd.read_csv(out_path)
        bullet_col = detect_bullet_col(existing.columns)
        if bullet_col is None:
            raise ValueError(f"No known bullet column found in checkpoint. Columns: {list(existing.columns)}")
        already_scored_bullets = set(existing[bullet_col].dropna().astype(str).tolist())
        results = existing.to_dict("records")
        cli_art.cli_info(f"Resuming from checkpoint: {len(results)} bullets already scored, skipping them.")
    except Exception as e:
        cli_art.friendly_warning(e, "reading the existing audit checkpoint", "starting this audit fresh instead")

total = len(df)
skipped = 0

for i, row in df.iterrows():
    bullet = str(row.get("Bullet Point") or row.get("bullet") or row.get("achievement") or row.to_dict())
    role_company = str(row.get("Role / Company", ""))

    # Skip if already scored in a previous run
    if bullet in already_scored_bullets:
        skipped += 1
        continue

    processed = len(results) - skipped + 1
    cli_art.console.print(f"  [{i+1}/{total}] {bullet[:60]}...", markup=False, soft_wrap=True)

    try:
        critique_text, usage = GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction=critique_system,
            contents=(
                f"--- BULLET ---\n{bullet}\n\n"
                f"--- ROLE / COMPANY (context only -- flag if the bullet redundantly restates this) ---\n{role_company}"
            ),
            response_schema=CritiqueSchema,
            temperature=0.0
        )
        data = GeminiClient.parse_json(critique_text)
        results.append({
            **row.to_dict(),
            "accuracy_score":      data.get("accuracy_score"),
            "believability_score": data.get("believability_score"),
            "clarity_score":       data.get("clarity_score"),
            "ats_value":           data.get("ats_value"),
            "manager_test":        data.get("manager_test"),
            "weaknesses":          data.get("weaknesses"),
        })
    except Exception as e:
        cli_art.friendly_warning(e, "scoring this bullet", "marking it ERROR so you can rerun the audit to retry it")
        results.append({**row.to_dict(), "manager_test": "ERROR", "weaknesses": f"[AUDIT_ERROR] {e}"})

    # --- CHECKPOINT SAVE after every bullet ---
    # Saved every time (cheap, and what makes a restart resumable), but
    # only reported at VERBOSE -- a line per bullet was pure spam at the
    # default output level.
    pd.DataFrame(results).to_csv(out_path, index=False)
    cli_art.detail(f"Checkpoint saved ({len(results)} bullets scored)")

    if i < total - 1:
        time.sleep(SLEEP)

error_count = sum(1 for r in results if r.get('manager_test') == 'ERROR')
cli_art.cli_success(f"Done. Results saved to {out_path}")
cli_art.cli_info(f"PASS:  {sum(1 for r in results if r.get('manager_test') == 'PASS')}")
cli_art.cli_info(f"FAIL:  {sum(1 for r in results if r.get('manager_test') == 'FAIL')}")
# A count of zero isn't an error -- only style it as one when something
# actually failed to score.
if error_count:
    cli_art.cli_warning(f"ERROR: {error_count}")
else:
    cli_art.cli_info(f"ERROR: {error_count}")
