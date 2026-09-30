"""NIM fallback for evaluation and embedding when Gemini quota is exhausted.

Eval: Gemini → Nemotron Super → Nemotron Ultra.
Embedding: Gemini ge2 → ge1 → nemotron-3-embed-1b.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"

SUPER_MODEL = "nvidia/nemotron-3-super-120b-a12b"
ULTRA_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"

SUPER_MAX_TOKENS = 8000
ULTRA_MAX_TOKENS = 16384

NIM_CONSECUTIVE_FAILURE_THRESHOLD = 3


def _nvidia_api_key() -> str | None:
    return os.environ.get("NVIDIA_API_KEY")


def _openai_sdk_importable() -> bool:
    """Whether the transport this module needs is actually installed.

    NIM speaks the OpenAI-compatible API, so the `openai` package is the
    transport (no OpenAI service is contacted). It was missing from
    requirements.txt, so nim_available() answered True on the key alone
    and every real call then raised ModuleNotFoundError -- at the eval
    site, which has no handler, that aborted a whole batch run. An
    availability check has to test the thing it claims is available.
    """
    import importlib.util

    return importlib.util.find_spec("openai") is not None


def nim_available() -> bool:
    if _is_test_env():
        return False
    if not _nvidia_api_key():
        return False
    return _openai_sdk_importable()


def _is_test_env() -> bool:
    import sys

    return "unittest" in sys.modules and not os.environ.get("RESUME_ALLOW_TEST_NETWORK")


def _make_client():
    from openai import OpenAI

    key = _nvidia_api_key()
    if not key:
        raise RuntimeError("NVIDIA_API_KEY not set")
    return OpenAI(base_url=NIM_BASE_URL, api_key=key)


def generate_with_nim(
    system_instruction: str,
    contents: str,
    # A Pydantic model CLASS (what every caller passes -- the same
    # `response_schema=` objects the Gemini path takes) or an already-
    # converted JSON-schema dict. Annotated `dict | None` originally, which
    # contradicted the .model_json_schema() call below and every call site.
    response_schema: Any = None,
) -> tuple[str | None, str]:
    """Try Super, then Ultra. Returns (json_text, model_used) or (None, "")."""
    client = _make_client()

    schema_instruction = ""
    if response_schema:
        try:
            schema_dict = response_schema.model_json_schema()
        except AttributeError:
            schema_dict = response_schema
        schema_instruction = (
            "\n\nRespond with valid JSON matching this schema exactly. "
            "Output ONLY the JSON object, no markdown fences or extra text.\n"
            f"{json.dumps(schema_dict, indent=2)}"
        )

    messages = [
        {"role": "system", "content": system_instruction + schema_instruction},
        {"role": "user", "content": contents},
    ]

    for model, max_tokens in [
        (SUPER_MODEL, SUPER_MAX_TOKENS),
        (ULTRA_MODEL, ULTRA_MAX_TOKENS),
    ]:
        try:
            logger.info("NIM fallback: trying %s", model)
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                seed=42,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content
            if text:
                text = text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                logger.info("NIM fallback: %s succeeded", model)
                return text, model
        except Exception:
            logger.warning("NIM fallback: %s failed", model, exc_info=True)
            continue

    logger.error("NIM fallback: all models exhausted")
    return None, ""


# ---------------------------------------------------------------------------
# Embedding via nemotron-3-embed-1b
# ---------------------------------------------------------------------------

NIM_EMBED_MODEL = "nvidia/nemotron-3-embed-1b"
NIM_EMBED_DIM = 2048
NIM_EMBED_FAMILY = "nem1b"


def embed_batch_nim(
    texts: list[str], input_type: str = "passage", max_retries: int = 3
) -> list[list[float]] | None:
    """Embed via NIM. input_type is 'passage' for indexing, 'query' for search."""
    if _is_test_env():
        return None
    key = _nvidia_api_key()
    if not key:
        return None

    from openai import OpenAI

    client = OpenAI(base_url=NIM_BASE_URL, api_key=key)

    for attempt in range(max_retries):
        try:
            resp = client.embeddings.create(
                model=NIM_EMBED_MODEL,
                input=texts,
                extra_body={"input_type": input_type, "truncate": "END"},
            )
            vecs = [d.embedding for d in resp.data]
            if len(vecs) != len(texts):
                logger.warning(
                    "NIM embed: sent %d texts, got %d back", len(texts), len(vecs)
                )
                return None
            return vecs
        except Exception:
            logger.warning(
                "NIM embed attempt %d/%d failed",
                attempt + 1,
                max_retries,
                exc_info=True,
            )
    return None
