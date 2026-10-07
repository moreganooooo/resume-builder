# Handoff: bullet work, role order, and rebuilds (2026-10-07)

Morgan is both engineer and candidate. Prefer root-cause fixes in prompt/rules over patching one resume. Constraints that must hold: no Treering/Mercor leaks, no self-taught tools claimed as experience, no "Salesforce Administrator", never tighten lenient Skills matching or lower keyword coverage. Pronouns unstated: use they/them.

## What was fixed

### 1. Role order (not chronological)
- **Cause:** `orchestrator._required_role_roster()` (~line 829) reads `roles:` from `profiles/morgan/knowledge_base/profile.yml`. `auto_fix_experience_order` (~1482) sorts EXPERIENCE by roster index only, and `validate_resume._check_role_order` checks against the roster. The roster was not date-sorted.
- **Fix:** reordered `roles:` newest to oldest: Mercor, Treering, Inside Sales Team, USitek, DeJoy Knauff & Blood, Element 8 / Strategy LLC, VML, Callahan Creek, OfficeTeam Adecco Greendox, KU Payroll Office.
- **Caveat:** `profile.yml` is gitignored and Syncthing-synced, so this change is NOT in git. Backup of the old file: `/private/tmp/claude-502/profile.yml.bak-roster` (may be cleared on reboot).
- **Test:** `tests/test_experience_order.py` (committed).

### 2. Bullets over-trimmed (root cause: prompt)
- **Cause:** `resume-engine/prompts/tailor_resume.md` (~lines 181-183) said "Target length: ~100 chars" and "~70% one-liners, ~30% two-liners". The model read the mix as a quota and compressed 150-230 char bullets to 99 chars or fewer, dropping result clauses. The old RemoteHunter build had 17 of 38 bullets flagged `task_only_bullets`.
- **Fix (commit `b768a7ab`, pushed):**
  - Prompt now says a bullet within 220 chars stays whole; never cut the outcome clause; compress only bullets over 220 chars or ones that would wrap to a widow under ~5 words; the 70/30 mix is descriptive, not a quota.
  - `resume-engine/rules/style_rules.yaml` `mix:` text updated the same way. Numeric limits unchanged (`one_liner_target_chars` 100, `one_liner_max_chars` 108, `two_liner_max_chars` 220, `widow_min_words` 5, `max_printed_lines` 2).
  - Test: `tests/test_bullet_length_prompt.py` (3 tests).
- **Also pushed:** `df9e75b6` (Gemma slim-tier reserves: `GEMMA_SYSTEM_PROMPT_RESERVE_CHARS = 17_000`, `GEMMA_SEGMENT_RESERVE_CHARS = 16_500`).

### 3. Clerical bullets are NOT missing outcomes
- `scripts/enrich_clerical_bullets.py` already ran. The bank (`bullet-bank-keepers-audited.csv`) has 37 "Morgan-confirmed" rows covering USitek, OfficeTeam/Adecco/Greendox, Payroll and DeJoy. Do NOT re-run it or claim the bank lacks outcomes. The earlier trimming was the prompt, not the bank.

## Rebuild state
- All five rebuilds exited 0: RemoteHunter, Black Box, Jeppesen, Opensesame, Testeract (`/private/tmp/claude-502/rebuild/status.txt`, `run.sh`).
- **RemoteHunter was re-run after the fix** (log: `rebuild/remotehunter-rerun.log`). Result: 2 pages, 100% JD-keyword coverage (12/12), DOCX written beside the PDF, order newest to oldest, 8 of 29 bullets at 99 chars or fewer (was 17 of 38 flagged), many bullets 140-170 chars.
- **Black Box very likely needs a re-run.** It started before the roster and prompt changes. Jeppesen, Opensesame and Testeract may also predate the prompt change; check their build times against commit `b768a7ab` before trusting their order/bullets. Completed JDs get renamed on each run, so look up the current name with `ls jds/morgan/completed | grep -i <company>` rather than using `run.sh`'s hardcoded names.
- Run a build: `source .venv/bin/activate && python scripts/orchestrator.py jds/morgan/completed/<file>`.

## Open issues found in the new RemoteHunter build (not yet fixed)
1. **Possible embellishment:** Inside Sales bullet "Promoted to sole manager of a 12-person team within six months, overseeing administrative processes". The bank says Top 10 of 100+ reps, promotion to lead a team, and coordinating a 12-member team. "Sole manager" and "within six months" look unsupported. Check the source and, if invented, find the root cause in the prompt/rules rather than editing the resume.
2. **Awkward wording:** "Consolidated information integrity across prospect lists..." and "Governed strict confidentiality...".
3. **Weak bullet:** KU Payroll, "Upheld strict confidentiality and followed compliance procedures" (64 chars).
4. **Summary warning:** no concrete metric beyond the years-of-experience figure.
5. **Bank mismatch (unverified):** the OfficeTeam and KU Payroll bullets don't obviously match the confirmed bank rows (e.g., the SCS offer bullet, the 500+ packets row). May be keyword-fitting for a data-entry JD; compare before assuming.
6. **Not checked on the new build:** the validator's `task_only_bullets` count, and a grep for "Salesforce Administrator" and self-taught tools.
7. **Validator false positive:** `task_only_bullets` flags "Received an offer of direct employment from SCS Engineers..." although it is a real outcome. Validator unchanged.
8. **Unchecked:** whether the page-fit trim loop also shortens bullets.

## Other pending items
- Gem scorer result to report to Morgan: 28 scored, 0 hidden gems, 0 strong, 0 errors; gems-only CSV at 202 rows.
- Confirm `dashboard_actions._tailor` writes a DOCX (RemoteHunter via the orchestrator does).
- Full unittest suite (~4.5 min) not run after the final commit.
- Pre-existing gofmt flag on `dashboard/.../pipeline.go`. Never stage untracked `.claude/*.md`.

## Environment notes
- RTK compresses output and can hide hook failures: use `rtk proxy git ...` or redirect to a file and Read it.
- Pre-commit hooks: black, isort, mypy, bandit, codespell, Conventional Commit. Tests: stdlib `unittest`, run with `.venv/` activated.
- GitHub has returned a spurious "Internal Server Error" on push before; verify with `git status -sb`.
- Scratch outputs in `/private/tmp/claude-502/`: `rh_bullets.txt`, `bank_check.txt`, `src_vs_out.txt`, `rh3.txt` (new build's bullets).
