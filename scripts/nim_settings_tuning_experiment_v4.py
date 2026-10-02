#!/usr/bin/env python3
"""Compatibility launcher for the NVIDIA settings-tuning experiment.

Your local nim_smoke_test_nvidia_v2.py differs slightly from the version that
was attached: it does not expose _prompt_only_messages. This launcher supplies
that missing helper in memory, then runs the complete standalone v3 experiment
unchanged. No existing benchmark file is edited.
"""

import json
from typing import Any

import nim_smoke_test_nvidia_v2 as nim


def _prompt_only_messages(
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
) -> list[dict[str, Any]]:
    """Append a portable JSON-only instruction without consecutive user turns."""
    copied = [dict(message) for message in messages]
    instruction = (
        "Reply with ONLY a JSON object matching this schema. "
        "No prose, markdown, or code fences.\n\n"
        f"Schema:\n{json.dumps(schema)}"
    )
    if copied and copied[-1].get("role") == "user":
        copied[-1]["content"] = f"{copied[-1].get('content', '')}\n\n{instruction}"
    else:
        copied.append({"role": "user", "content": instruction})
    return copied


# Supply the compatibility helper before importing v3. v3 uses the same loaded
# nim module object, so its _fixed_structured_call sees this function at runtime.
nim._prompt_only_messages = _prompt_only_messages

import nim_settings_tuning_experiment_v3 as experiment  # noqa: E402

if __name__ == "__main__":
    experiment.main()
