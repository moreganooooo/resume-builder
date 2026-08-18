"""
render_txt.py -- Plain ASCII Text Resume Generator.

Generates tab-aligned, clean plain ASCII text versions of resumes optimized for
copy-pasting into legacy ATS text boxes or plain-text email applications.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

from export_formats import render_plaintext


def render_txt_from_json(json_path: str, output_txt_path: Optional[str] = None) -> str:
    """Reads a resume JSON file and writes/returns a plain ASCII text version."""
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"Resume JSON not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    txt_content = render_plaintext(data)

    if output_txt_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_txt_path)), exist_ok=True)
        with open(output_txt_path, "w", encoding="utf-8") as f:
            f.write(txt_content)

    return txt_content


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render plain ASCII text resume from JSON."
    )
    parser.add_argument("json_file", help="Path to resume JSON file")
    parser.add_argument(
        "-o", "--output", help="Optional output .txt path", default=None
    )
    args = parser.parse_args(argv)

    try:
        content = render_txt_from_json(args.json_file, args.output)
        if not args.output:
            print(content)
        else:
            print(f"✓ Plain text resume saved to {args.output}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
