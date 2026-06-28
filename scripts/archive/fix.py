# ARCHIVED — one-time patch script, no longer called by anything.
# Original purpose: deduplicate bullet-bank-keepers.csv by 'Bullet Point' column.
# Superseded by the audit pipeline in audit_keepers.py.
# Kept here for reference only. Do not re-add to the active pipeline.
#
# Original code preserved below:
# ---
import pandas as pd
df = pd.read_csv("resume-engine/knowledge_base/bullet-bank-keepers.csv")
before = len(df)
df = df.drop_duplicates(subset=["Bullet Point"])
after = len(df)
print(f"Removed {before - after} duplicates. {after} keepers remain.")
df.to_csv("resume-engine/knowledge_base/bullet-bank-keepers.csv", index=False)
