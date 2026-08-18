#!/usr/bin/env python3
"""Capture TUI visual snapshots (PNG/GIF) for visual inspection and AI design review.

Supports two rendering backends:
1. VHS (if installed) using .tape scripts in dashboard/tapes/
2. Headless Playwright / ANSI-to-HTML rendering using dashboard/cmd/rendercapture
"""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "artifacts")


def parse_ansi_to_html(ansi_text: str) -> str:
    """Convert ANSI escape sequences to styled HTML with Catppuccin Mocha theme."""
    # Strip carriage returns and nulls
    cleaned = ansi_text.replace("\r", "")
    escaped = html.escape(cleaned)

    # Basic ANSI color map
    color_map = {
        "30": "#45475a",  # Surface1
        "31": "#f38ba8",  # Red
        "32": "#a6e3a1",  # Green
        "33": "#f9e2af",  # Yellow
        "34": "#89b4fa",  # Blue
        "35": "#cba6f7",  # Mauve
        "36": "#94e2d5",  # Teal
        "37": "#cdd6f4",  # Text
        "90": "#585b70",  # Surface2
        "91": "#eba0ac",  # Maroon
        "92": "#a6e3a1",  # Green
        "93": "#fab387",  # Peach
        "94": "#89dceb",  # Sky
        "95": "#f5c2e7",  # Pink
        "96": "#74c7ec",  # Sapphire
        "97": "#ffffff",  # White
    }

    # Replace SGR color codes
    def replace_sgr(match: re.Match) -> str:
        codes = match.group(1).split(";")
        styles = []
        for code in codes:
            if code == "1":
                styles.append("font-weight:bold")
            elif code == "2":
                styles.append("opacity:0.7")
            elif code == "3":
                styles.append("font-style:italic")
            elif code == "4":
                styles.append("text-decoration:underline")
            elif code in color_map:
                styles.append(f"color:{color_map[code]}")
            elif code.startswith("38;2;"):  # 24-bit RGB foreground
                parts = code.split(";")
                if len(parts) >= 5:
                    styles.append(f"color:rgb({parts[2]},{parts[3]},{parts[4]})")
            elif code.startswith("48;2;"):  # 24-bit RGB background
                parts = code.split(";")
                if len(parts) >= 5:
                    styles.append(
                        f"background-color:rgb({parts[2]},{parts[3]},{parts[4]})"
                    )
            elif code == "0":
                return "</span>"

        if styles:
            return f'<span style="{";".join(styles)}">'
        return ""

    ansi_regex = re.compile(r"\x1b\[([0-9;]*)m")
    formatted = ansi_regex.sub(replace_sgr, escaped)
    # Strip any remaining unhandled escape codes
    formatted = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", formatted)

    html_doc = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'JetBrains Mono', 'Fira Code', 'Menlo', monospace;
    font-size: 13px;
    line-height: 1.25;
    margin: 0;
    padding: 20px;
    display: inline-block;
  }}
  pre {{
    margin: 0;
    white-space: pre;
    font-family: inherit;
  }}
</style>
</head>
<body>
<pre>{formatted}</pre>
</body>
</html>"""
    return html_doc


def capture_with_vhs(tape_name: str) -> bool:
    """Run a VHS tape to produce PNG/GIF artifacts."""
    vhs_path = shutil.which("vhs")
    if not vhs_path:
        return False

    tape_path = os.path.join(PROJECT_ROOT, "dashboard", "tapes", f"{tape_name}.tape")
    if not os.path.exists(tape_path):
        print(f"[!] VHS tape not found: {tape_path}")
        return False

    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    print(f"[*] Running VHS tape: {tape_path}...")
    res = subprocess.run([vhs_path, tape_path], cwd=PROJECT_ROOT)
    return res.returncode == 0


def capture_with_rendercapture(output_png: str) -> bool:
    """Run dashboard/cmd/rendercapture, convert ANSI to HTML, and snapshot with Playwright."""
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    go_bin = shutil.which("go")
    if not go_bin:
        print("[!] Go binary not found.")
        return False

    # Execute rendercapture
    print("[*] Running headless dashboard rendercapture...")
    render_proc = subprocess.run(
        [go_bin, "run", "./cmd/rendercapture"],
        cwd=os.path.join(PROJECT_ROOT, "dashboard"),
        capture_output=True,
        text=True,
    )
    if render_proc.returncode != 0:
        print(f"[!] rendercapture failed: {render_proc.stderr}")
        return False

    raw_output_file = "/tmp/dashboard_render.txt"
    if not os.path.exists(raw_output_file):
        print("[!] Expected /tmp/dashboard_render.txt not generated.")
        return False

    with open(raw_output_file, "r", encoding="utf-8") as f:
        ansi_content = f.read()

    html_content = parse_ansi_to_html(ansi_content)
    tmp_html = os.path.join(ARTIFACTS_DIR, "preview.html")
    with open(tmp_html, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Use Node/Playwright to render HTML to PNG
    js_renderer = os.path.join(PROJECT_ROOT, "scripts", "screenshot-html.mjs")
    node_bin = shutil.which("node")
    if node_bin and os.path.exists(js_renderer):
        print(f"[*] Rendering {tmp_html} to {output_png} via Playwright...")
        res = subprocess.run(
            [node_bin, js_renderer, tmp_html, output_png], cwd=PROJECT_ROOT
        )
        return res.returncode == 0

    print(f"[✓] Rendered HTML preview saved to {tmp_html}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Capture TUI visual snapshots for inspection"
    )
    parser.add_argument(
        "--screen",
        choices=["menu", "pipeline", "jobs", "kb_view", "mobile", "all"],
        default="all",
        help="Screen tape to capture",
    )
    parser.add_argument(
        "--vhs", action="store_true", help="Force using VHS tape runner"
    )
    parser.add_argument(
        "--out",
        default=os.path.join(ARTIFACTS_DIR, "tui_capture.png"),
        help="Output PNG path",
    )
    args = parser.parse_args()

    if args.vhs or shutil.which("vhs"):
        screens = (
            ["menu", "pipeline", "jobs", "kb_view", "mobile"]
            if args.screen == "all"
            else [args.screen]
        )
        for s in screens:
            capture_with_vhs(s)
    else:
        print("[*] VHS not detected; using headless Go + Playwright snapshot engine.")
        capture_with_rendercapture(args.out)


if __name__ == "__main__":
    main()
