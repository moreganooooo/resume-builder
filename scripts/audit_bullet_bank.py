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
import theme

SLEEP = 8  # seconds between calls — generous since this is a one-time offline task

engine = ResumeEngine()
critique_prompt = engine.load_prompt("critique_bullet.md")
manager_test_rules = json.dumps(engine.load_yaml(engine.scoring_dir, "manager_test.yaml"))
believability_rules = json.dumps(engine.load_yaml(engine.scoring_dir, "believability.yaml"))

critique_system = (
    f"\n\n{critique_prompt}"
    f"\n\nRULES:\n{manager_test_rules}"
    f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
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
        print(f"{theme.ICONS['resume']}  Resuming from checkpoint: {len(results)} bullets already scored, skipping them.")
    except Exception as e:
        print(f"{theme.ICONS['warning']}  Could not read existing checkpoint ({e}). Starting fresh.")

total = len(df)
skipped = 0

for i, row in df.iterrows():
    bullet = str(row.get("Bullet Point") or row.get("bullet") or row.get("achievement") or row.to_dict())

    # Skip if already scored in a previous run
    if bullet in already_scored_bullets:
        skipped += 1
        continue

    processed = len(results) - skipped + 1
    print(f"  [{i+1}/{total}] {bullet[:60]}...")

    try:
        critique_text, usage = GeminiClient.generate(
            model="gemini-3.1-flash-lite",
            system_instruction=critique_system,
            contents=bullet,
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
        print(f"  {theme.ICONS['warning']} Error: {e}")
        results.append({**row.to_dict(), "manager_test": "ERROR", "weaknesses": str(e)})

    # --- CHECKPOINT SAVE after every bullet ---
    pd.DataFrame(results).to_csv(out_path, index=False)
    print(f"   {theme.ICONS['save']} Checkpoint saved ({len(results)} bullets scored)")

    if i < total - 1:
        time.sleep(SLEEP)

print(f"\n{theme.ICONS['success']} Done. Results saved to {out_path}")
print(f"   PASS:  {sum(1 for r in results if r.get('manager_test') == 'PASS')}")
print(f"   FAIL:  {sum(1 for r in results if r.get('manager_test') == 'FAIL')}")
print(f"   ERROR: {sum(1 for r in results if r.get('manager_test') == 'ERROR')}")
