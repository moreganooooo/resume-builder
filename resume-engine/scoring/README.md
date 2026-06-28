# resume-engine/scoring/

This folder holds YAML scoring rubrics consumed at runtime by `orchestrator.py` 
and `score_keeper_gems.py`.

## Files that belong here

| File | Used by | Purpose |
|---|---|---|
| `manager_test.yaml` | `orchestrator.py` | Pass/fail rules the Skeptical Editor uses to judge bullets |
| `believability.yaml` | `orchestrator.py`, `score_keeper_gems.py` | Rubric for believability scoring (0-100) |
| `ai_risk.yaml` | `orchestrator.py` | Definitions of high-risk AI-sounding language patterns |

## Status

⚠️ **This folder is currently empty.** The scoring YAML files are expected here 
but have not been committed yet. `orchestrator.py` handles missing files gracefully 
(falls back to `{}` via `load_yaml`), but the scoring rules will not apply until 
these files are added.

## Next step

Create `manager_test.yaml`, `believability.yaml`, and `ai_risk.yaml` in this folder. 
See `resume-engine/rules/` for the format/style reference.
