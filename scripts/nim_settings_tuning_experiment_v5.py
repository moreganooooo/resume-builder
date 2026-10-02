#!/usr/bin/env python3
"""Run the final NVIDIA settings experiment against the actual local v2 helper.

The actual nim_smoke_test_nvidia_v2.py exposes stage_ping() and
_append_json_instruction(), rather than the warmup() and
_prompt_only_messages() names assumed by earlier wrappers. This launcher adds
those two compatibility aliases in memory, then executes the complete v3
experiment. It does not edit any existing benchmark file.
"""

import nim_smoke_test_nvidia_v2 as nim


def warmup(client, model):
    """Compatibility warm-up using the v2 helper's existing ping stage."""
    result = nim.stage_ping(client, model)
    status = "ok" if result["ok"] else "FAILED"
    print(f" warmup {status} in {result['seconds']}s ({result.get('diagnosis', '')})")
    return result


# Alias the actual v2 helper names before importing v3. The v3 experiment uses
# this same module object at runtime, so both compatibility hooks are present.
nim.warmup = warmup
nim._prompt_only_messages = nim._append_json_instruction

import nim_settings_tuning_experiment_v3 as experiment  # noqa: E402

if __name__ == "__main__":
    experiment.main()
