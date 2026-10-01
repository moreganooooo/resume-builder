#!/usr/bin/env python3
"""Compatibility-safe NVIDIA NIM helper v3.

This is a drop-in wrapper around your working nim_smoke_test_nvidia_v2.py.
It fixes the only discovered v2 runtime defect: structured-output routes can
now merge a caller's extra_body (for example Lightning thinking settings) with
the route's guided_json extra_body instead of passing extra_body twice.
"""

from typing import Any

import nim_smoke_test_nvidia_v2 as _base

# Re-export the public and underscore-prefixed helpers the existing benchmark
# scripts use, so this module remains a drop-in replacement for v2.
BASE_URL = _base.BASE_URL
DEFAULT_MODEL = _base.DEFAULT_MODEL
PROJECT_ROOT = _base.PROJECT_ROOT
RESULTS_DIR = _base.RESULTS_DIR
REASONING_EFFORTS = _base.REASONING_EFFORTS
MODEL_SETTINGS = _base.MODEL_SETTINGS
SYSTEMLESS_MODELS = _base.SYSTEMLESS_MODELS
STRUCTURED_OUTPUT_MODELS = _base.STRUCTURED_OUTPUT_MODELS

_client = _base._client
_save = _base._save
_call = _base._call
_merge = _base._merge
_prompt_only_messages = _base._prompt_only_messages
apply_settings = _base.apply_settings
effort_override = _base.effort_override
warmup = _base.warmup


def _structured_call(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Try JSON routes without duplicating extra_body keyword arguments.

    Lightning's settings experiment passes its own extra_body containing
    chat_template_kwargs.enable_thinking and reasoning_budget. The guided_json
    fallback route adds guided_json to extra_body. Both must be merged into a
    single dict before calling _call().
    """
    routes: list[tuple[str, dict[str, Any], list[dict[str, Any]]]] = [
        (
            "response_format.json_schema",
            {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "result",
                        "schema": schema,
                        "strict": True,
                    },
                }
            },
            messages,
        ),
        ("guided_json", {"extra_body": {"guided_json": schema}}, messages),
        ("prompt_only", {}, _prompt_only_messages(messages, schema)),
    ]

    if model not in STRUCTURED_OUTPUT_MODELS:
        routes = routes[-1:]

    rejected: list[dict[str, str]] = []
    for mode, additions, route_messages in routes:
        call_kwargs = dict(kwargs)
        route_extra_body = additions.get("extra_body")

        if route_extra_body:
            call_kwargs["extra_body"] = _merge(
                call_kwargs.get("extra_body") or {},
                route_extra_body,
            )

        call_kwargs.update(
            {key: value for key, value in additions.items() if key != "extra_body"}
        )

        result = _call(client, model, route_messages, **call_kwargs)
        result["mode"] = mode
        if result["ok"]:
            result["rejected_routes"] = rejected
            return result

        rejected.append({"mode": mode, "error": result["error"][:220]})

    result["rejected_routes"] = rejected
    return result
