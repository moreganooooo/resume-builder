"""
patch_engine.py -- RFC 6902 JSON Patch Surgical Bullet Repair Engine.

Implements surgical JSON Patch (RFC 6902) operations on resume JSON structures.
Allows replacing, adding, or modifying specific failing bullets without re-prompting
or regenerating the entire resume document.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional, Tuple, Union


class JsonPatchError(ValueError):
    """Raised when an RFC 6902 JSON patch operation cannot be applied."""


def parse_json_pointer(pointer: str) -> List[Union[str, int]]:
    """
    Parses an RFC 6901 JSON pointer into tokens.
    e.g., '/experience/0/bullets/1' -> ['experience', 0, 'bullets', 1]
    """
    if not pointer:
        return []
    if not pointer.startswith("/"):
        raise JsonPatchError(f"Invalid JSON Pointer (must start with '/'): {pointer}")

    raw_tokens = pointer[1:].split("/")
    tokens: List[Union[str, int]] = []
    for t in raw_tokens:
        decoded = t.replace("~1", "/").replace("~0", "~")
        if decoded.isdigit():
            tokens.append(int(decoded))
        else:
            tokens.append(decoded)
    return tokens


def _navigate_to_parent(doc: Any, tokens: List[Union[str, int]], path: str) -> Any:
    """Walks every token but the last, returning the container to operate on."""
    curr = doc
    for token in tokens[:-1]:
        if isinstance(curr, list):
            if not isinstance(token, int) or token < 0 or token >= len(curr):
                raise JsonPatchError(
                    f"Array index out of bounds at token '{token}' in path '{path}'"
                )
            curr = curr[token]
        elif isinstance(curr, dict):
            if token not in curr:
                raise JsonPatchError(f"Key '{token}' not found in path '{path}'")
            curr = curr[token]
        else:
            raise JsonPatchError(
                f"Cannot navigate into primitive at token '{token}' in path '{path}'"
            )
    return curr


def _checked_index(
    target: List[Any], token: Union[str, int], message: str, *, allow_end: bool = False
) -> int:
    """Validates a list index token, raising JsonPatchError with `message`.

    `allow_end` permits len(target) itself, which RFC 6902 'add' uses to mean
    "append" -- every other op needs an index that already exists.
    """
    limit = len(target) if allow_end else len(target) - 1
    if not isinstance(token, int) or token < 0 or token > limit:
        raise JsonPatchError(message)
    return token


def _op_replace(
    curr: Any, last_token: Union[str, int], operation: Dict[str, Any], path: str
) -> None:
    value = operation.get("value")
    if isinstance(curr, list):
        idx = _checked_index(
            curr,
            last_token,
            f"Index {last_token} out of bounds for replace in path '{path}'",
        )
        curr[idx] = value
    elif isinstance(curr, dict):
        if last_token not in curr:
            raise JsonPatchError(
                f"Key '{last_token}' not in dict for replace in path '{path}'"
            )
        curr[last_token] = value
    else:
        raise JsonPatchError(
            f"Cannot replace on non-collection target at path '{path}'"
        )


def _op_add(
    curr: Any, last_token: Union[str, int], operation: Dict[str, Any], path: str
) -> None:
    value = operation.get("value")
    if isinstance(curr, list):
        if last_token == "-":
            curr.append(value)
            return
        if not isinstance(last_token, int):
            raise JsonPatchError(f"Invalid list index '{last_token}' in add operation")
        idx = _checked_index(
            curr,
            last_token,
            f"Index {last_token} out of bounds for add in path '{path}'",
            allow_end=True,
        )
        curr.insert(idx, value)
    elif isinstance(curr, dict):
        curr[str(last_token)] = value
    else:
        raise JsonPatchError(f"Cannot add on non-collection target at path '{path}'")


def _op_remove(
    curr: Any, last_token: Union[str, int], operation: Dict[str, Any], path: str
) -> None:
    del operation  # remove carries no value
    if isinstance(curr, list):
        idx = _checked_index(
            curr,
            last_token,
            f"Index {last_token} out of bounds for remove in path '{path}'",
        )
        del curr[idx]
    elif isinstance(curr, dict):
        if last_token not in curr:
            raise JsonPatchError(
                f"Key '{last_token}' not found for remove in path '{path}'"
            )
        del curr[last_token]
    else:
        raise JsonPatchError(
            f"Cannot remove from non-collection target at path '{path}'"
        )


def _op_test(
    curr: Any, last_token: Union[str, int], operation: Dict[str, Any], path: str
) -> None:
    del path  # the failure messages here name the token, not the pointer
    expected_value = operation.get("value")
    actual_value = None
    if isinstance(curr, list):
        idx = _checked_index(
            curr, last_token, f"Test failed: index {last_token} out of bounds"
        )
        actual_value = curr[idx]
    elif isinstance(curr, dict):
        if last_token not in curr:
            raise JsonPatchError(f"Test failed: key '{last_token}' not found")
        actual_value = curr[last_token]
    if actual_value != expected_value:
        raise JsonPatchError(
            f"Test operation failed: expected {expected_value}, got {actual_value}"
        )


_OPERATIONS = {
    "replace": _op_replace,
    "add": _op_add,
    "remove": _op_remove,
    "test": _op_test,
}


def apply_operation(doc: Any, operation: Dict[str, Any]) -> Any:
    """
    Applies a single RFC 6902 operation (replace, add, remove, test) to the document.
    Returns the modified document.
    """
    op = operation.get("op")
    path = operation.get("path")
    if not op or path is None:
        raise JsonPatchError(
            f"Malformed operation (missing 'op' or 'path'): {operation}"
        )

    tokens = parse_json_pointer(path)
    if not tokens:
        if op == "replace":
            return operation.get("value")
        raise JsonPatchError("Root path modification not supported for op: " + str(op))

    handler = _OPERATIONS.get(op)
    if handler is None:
        raise JsonPatchError(f"Unsupported operation '{op}'")

    handler(_navigate_to_parent(doc, tokens, path), tokens[-1], operation, path)
    return doc


def apply_patch(doc: Dict[str, Any], patch: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Applies a list of RFC 6902 JSON patch operations to a document copy.
    Returns the new document.
    """
    result = copy.deepcopy(doc)
    for op in patch:
        result = apply_operation(result, op)
    return result


def create_bullet_replace_patch(
    role_idx: int, bullet_idx: int, new_bullet_text: str
) -> Dict[str, Any]:
    """Generates an RFC 6902 replace operation for a specific bullet."""
    return {
        "op": "replace",
        "path": f"/experience/{role_idx}/bullets/{bullet_idx}",
        "value": new_bullet_text,
    }


def patch_resume_bullet(
    resume_data: Dict[str, Any],
    role_idx: int,
    bullet_idx: int,
    new_bullet_text: str,
) -> Dict[str, Any]:
    """
    Surgically replaces a single bullet at experience[role_idx].bullets[bullet_idx]
    using RFC 6902 semantics.
    """
    patch = [create_bullet_replace_patch(role_idx, bullet_idx, new_bullet_text)]
    return apply_patch(resume_data, patch)


def main() -> None:
    """CLI execution entrypoint."""
    print(
        "\n\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m"
    )
    print(
        "  \033[1m\033[38;2;139;117;255m◈ RESUME-BUILDER RFC 6902 JSON PATCH ENGINE\033[0m"
    )
    print(
        "\033[1m\033[38;2;139;117;255m✦ ────────────────────────────────────────────────────────────── ✦\033[0m\n"
    )
    print(
        "  \033[1m\033[38;2;0;164;255mSurgical JSON Patch Bullet Repair Engine:\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ RFC 6901 JSON Pointer Parsing\033[0m   \033[38;2;163;163;163m(e.g., /experience/0/bullets/1)\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ RFC 6902 Operations\033[0m            \033[38;2;163;163;163m(replace, add, remove, test)\033[0m"
    )
    print(
        "    \033[1m\033[38;2;18;199;143m✓ In-Place Bullet Repair\033[0m         \033[38;2;163;163;163m(zero-token surgical replacement)\033[0m\n"
    )


if __name__ == "__main__":
    main()
