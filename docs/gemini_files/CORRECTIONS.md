# Corrections to prior session documents in this directory

Added after the remediation pass in `docs/review/onboarding_and_remediation_guide.md`
(Tasks 4.1–4.3, findings F19–F21). These files are kept as historical record of
prior Antigravity/Gemini sessions' work, but a few specific claims in them do
not match the current codebase and shouldn't be trusted at face value by a
future read (including a future me).

## `refactoring_plan.md`

- **"#1 TUI/UX: ...clean Unicode glyphs as the universal default icon
  standard...unless `RESUME_BUILDER_ICONS=nerd` is set" — FALSE for the case
  that matters.** Direct read of `scripts/theme.py`'s `_resolve_icon_set_name()`
  confirms Nerd Font remains the default for a real interactive terminal
  session (`sys.stdin.isatty()` → `"nerd"`); Unicode is only the default for
  non-interactive/piped contexts. This matches CLAUDE.md's own documented
  behavior. Any machine showing `unicode` in `resume doctor`'s Icon set line
  got there via a *persisted per-profile choice*, not a changed default.

- **"#10 Bullet Bank Engine: ...pure Python clustering algorithms" / "#13
  Dependencies: Pure Python/Go entry points with standard library
  fallbacks" — FALSE.** `pandas`/`numpy` remain unconditionally imported at
  module level in both `scripts/cluster_bullet_bank.py` and
  `scripts/orchestrator.py`. Nothing was removed. See the `mobile_and_install_setup_plan.md`
  note below for why this specific false claim has a real, concrete
  consequence beyond just being inaccurate.

- **"#17 Mobile Compatibility: ...COMPLETED"** — contradicted by
  `audit_report.md`'s own 🔴 CRITICAL rating for the identical dimension in
  the same file set (Playwright/Selenium binaries don't run on Android ARM).
  Not independently re-verified against a real Termux device in this pass —
  see the open item below.

## `mobile_and_install_setup_plan.md`

- **§3 "Mobile-Lite Footprint Option... excluding compiling heavy
  Pandas, NumPy, and Selenium... shrinks the environment from 250 MB to
  under 15 MB" — describes something that doesn't work today.** Because the
  pandas/numpy removal above never happened, `orchestrator.py` — the module
  every pipeline entry point imports — would raise `ModuleNotFoundError` the
  moment anyone actually used a "Mobile Lite" install to run `resume run` or
  any tailoring command. Treat this section as aspirational/future work, not
  a working setup path, until `orchestrator.py`'s pandas/numpy usage is
  actually made optional (a real scope-of-work item — see
  `docs/review/onboarding_and_remediation_guide.md` Task 4.2, Path B — not
  started, since mobile support isn't confirmed as an active near-term goal).
- The narrative in this document refers to the user as "Dom" with "his Pixel
  10" throughout — confirmed **not** a hallucination; that's a real second
  user (with ADHD) who will actually be testing the mobile path on a real
  Pixel 10 at some point. Flagging only because it looked like a name
  mismatch on first read, given the profile in this repo is `morgan`.

## Open item: settle the Mobile Compatibility contradiction for real

Neither this session nor the prior ones actually ran `npx playwright install
chromium` on a real Termux/Android-ARM device — `refactoring_plan.md`'s
"COMPLETED" and `audit_report.md`'s "CRITICAL" are both unverified claims
about the same open question. Playwright's own platform support matrix
suggests `audit_report.md` is more likely correct (no Android/ARM builds),
but this needs an actual device test to close out — see
`docs/review/onboarding_and_remediation_guide.md` Task 4.3 for the exact
commands to run. Good candidate for Dom's Pixel 10, whenever that happens.
