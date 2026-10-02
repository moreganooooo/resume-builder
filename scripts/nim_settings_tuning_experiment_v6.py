#!/usr/bin/env python3
"""Final compatibility launcher for the NVIDIA settings-tuning experiment.

The actual local nim_smoke_test_nvidia_v2.py uses these names:
  stage_ping             instead of warmup
  _append_json_instruction instead of _prompt_only_messages
  _merge_dicts           instead of _merge

This launcher supplies the three aliases in memory, then runs the complete v3
experiment unchanged. It does not modify any existing local benchmark file.
"""

import nim_smoke_test_nvidia_v2 as nim


def warmup(client, model):
    result = nim.stage_ping(client, model)
    status = "ok" if result["ok"] else "FAILED"
    print(f" warmup {status} in {result['seconds']}s ({result.get('diagnosis', '')})")
    return result


nim.warmup = warmup
nim._prompt_only_messages = nim._append_json_instruction
nim._merge = nim._merge_dicts

import nim_settings_tuning_experiment_v3 as experiment  # noqa: E402

if __name__ == "__main__":
    experiment.main()
