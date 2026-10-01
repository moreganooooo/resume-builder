#!/usr/bin/env python3
"""Run the NVIDIA settings experiment using the v3 structured-output fix.

This wrapper intentionally reuses the complete working experiment logic in
nim_settings_tuning_experiment.py and swaps only its shared helper module from
v2 to v3. It prevents the Lightning thinking + guided_json extra_body collision
without requiring any manual find/replace.
"""

import nim_settings_tuning_experiment as experiment
import nim_smoke_test_nvidia_v3 as nim

# Every function in the experiment resolves `nim` through that module's global
# namespace at runtime, so this replacement applies to all eval/rewrite calls.
experiment.nim = nim

if __name__ == "__main__":
    experiment.main()
