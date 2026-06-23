import pandas as pd
df = pd.read_csv("resume-engine/knowledge_base/bullet-bank-keepers.csv")
before = len(df)
df = df.drop_duplicates(subset=["Bullet Point"])
after = len(df)
print(f"Removed {before - after} duplicates. {after} keepers remain.")
df.to_csv("resume-engine/knowledge_base/bullet-bank-keepers.csv", index=False)