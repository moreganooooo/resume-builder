import os
import json
import time
import pandas as pd
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# Import shared objects from orchestrator
import sys
sys.path.insert(0, SCRIPT_DIR)
from orchestrator import client, CritiqueSchema, GeminiClient, ResumeEngine

SLEEP = 5  # seconds between calls — generous since this is a one-time offline task

engine = ResumeEngine()
critique_prompt = engine._load_prompt("critique_bullet.md")
manager_test_rules = json.dumps(engine._load_yaml(engine.scoring_dir, "manager_test.yaml"))
believability_rules = json.dumps(engine._load_yaml(engine.scoring_dir, "believability.yaml"))

critique_system = (
    f"\n\n{critique_prompt}"
    f"\n\nRULES:\n{manager_test_rules}"
    f"\n\nBELIEVABILITY RULES:\n{believability_rules}"
)

csv_path = os.path.join(engine.kb_dir, "bullet-bank-clean.csv")
df = pd.read_csv(csv_path)

results = []

for i, row in df.iterrows():
    bullet = str(row.get("bullet") or row.get("achievement") or row.to_dict())
    print(f"Auditing bullet {i+1}/{len(df)}: {bullet[:60]}...")

    try:
        critique_text = client.generate(
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
        print(f"  ⚠️ Error: {e}")
        results.append({**row.to_dict(), "manager_test": "ERROR", "weaknesses": str(e)})

    if i < len(df) - 1:
        time.sleep(SLEEP)

out_path = os.path.join(engine.kb_dir, "bullet-bank-audited.csv")
pd.DataFrame(results).to_csv(out_path, index=False)
print(f"\n✅ Done. Results saved to {out_path}")
print(f"   PASS: {sum(1 for r in results if r.get('manager_test') == 'PASS')}")
print(f"   FAIL: {sum(1 for r in results if r.get('manager_test') == 'FAIL')}")