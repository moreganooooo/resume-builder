"""
skills_menu.py -- Interactive profile skills / verified tools editor.
Allows users to add, edit, and delete tools/skills stored under
verified_tools.json in their active profile's knowledge base.
"""

import json
import os
import sys
from typing import cast

import charm_prompt
import cli_art
import profile_paths
import questionary
from atomic_write import atomic_write


def _pause() -> None:
    """run_skills_menu() and _view_skill_details() clear the screen at the
    top of their loops under alt-screen, so a result message printed right
    before returning to them was erased the instant it drew -- the same bug
    menu._handle_help() had."""
    import menu

    menu._pause_and_return()


def _get_verified_tools_path() -> str:
    kb_dir = profile_paths.kb_dir()
    return os.path.join(kb_dir, "verified_tools.json")


def _load_verified_tools() -> dict:
    path = _get_verified_tools_path()
    if not os.path.exists(path):
        return {
            "_meta": {
                "source": "manual",
                "last_updated": "",
                "total_entries": 0,
                "note": "Confidence reflects depth of documented use in archive evidence.",
            },
            "tools": [],
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            return cast("dict", json.load(f))
    except Exception as e:
        # Do NOT fall back to an empty skeleton here. The caller edits
        # whatever this returns and saves it straight back over the same
        # path, so handing back {"tools": []} for a file that merely
        # failed to parse turns a transient read error into permanent
        # deletion of every tool in the ledger. Raising keeps the file on
        # disk intact and surfaces the real problem.
        cli_art.display_error(
            f"Failed to read verified_tools.json: {e}. Refusing to continue, "
            "because saving now would overwrite the file with an empty list."
        )
        raise


def _save_verified_tools(data: dict) -> bool:
    path = _get_verified_tools_path()
    try:
        # Update meta counters
        if "_meta" not in data:
            data["_meta"] = {}
        data["_meta"]["total_entries"] = len(data.get("tools", []))
        import datetime

        data["_meta"]["last_updated"] = datetime.date.today().isoformat()

        with atomic_write(path, encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        cli_art.display_error(f"Failed to save verified_tools.json: {e}")
        _pause()
        return False


def _get_dismissed_skills_path() -> str:
    kb_dir = profile_paths.kb_dir()
    return os.path.join(kb_dir, "dismissed_skills.json")


def _load_dismissed_skills() -> list:
    """Skill/tool names explicitly marked "not part of my background" via
    skill_gap_scan.py's negative selector. Excluded from every future
    pending-pipeline scan so the candidate checkbox list doesn't keep
    re-offering the same irrelevant names run after run."""
    path = _get_dismissed_skills_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return cast("list", json.load(f).get("dismissed", []))
    except Exception:
        return []


def _save_dismissed_skills(names: list) -> bool:
    path = _get_dismissed_skills_path()
    try:
        import datetime

        data = {
            "dismissed": sorted(
                {n.strip() for n in names if n and n.strip()}, key=str.lower
            ),
            "_meta": {"last_updated": datetime.date.today().isoformat()},
        }
        with atomic_write(path, encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        cli_art.display_error(f"Failed to save dismissed_skills.json: {e}")
        _pause()
        return False


def _manage_dismissed_skills():
    """Lets the user un-dismiss a skill, in case one was hidden by
    mistake -- otherwise a wrong dismissal would be permanent."""
    dismissed = _load_dismissed_skills()
    if not dismissed:
        cli_art.detail(
            'No dismissed skills yet. Skills you mark as "not applicable" '
            "during a Pending Pipeline Skill Gap Scan show up here.",
            level=cli_art.NORMAL,
        )
        _pause()
        return

    cli_art.detail(
        f"{len(dismissed)} dismissed skill(s). Click or press space to "
        "toggle, a to select/deselect everything shown, / to filter.",
        level=cli_art.NORMAL,
    )
    choices = [questionary.Choice(name, name) for name in sorted(dismissed)]
    selected = cli_art.checkbox(
        "Select any to restore (they'll be eligible to reappear in future scans):",
        choices=choices,
        grid=True,
    )
    if not selected:
        return

    remaining = [n for n in dismissed if n not in selected]
    if _save_dismissed_skills(remaining):
        cli_art.display_success(
            f"Restored {len(selected)} skill(s): {', '.join(selected)}"
        )
        _pause()


def _generate_next_id(tools: list) -> str:
    highest = 0
    for t in tools:
        tid = t.get("id", "")
        if tid.startswith("tool_"):
            try:
                num = int(tid.split("_")[1])
                highest = max(highest, num)
            except ValueError:
                pass
    return f"tool_{highest + 1:03d}"


def _by_category(tools: list) -> dict:
    """Groups tools by category name.

    `or`, not a .get() default: a key that is PRESENT but null (possible
    from a merged/extracted ledger entry) returned None, and sorting None
    against str raised TypeError and took the whole Skills screen down.
    """
    categories: dict = {}
    for t in tools:
        categories.setdefault(t.get("category") or "Uncategorized", []).append(t)
    return categories


def _duplicate_names(tools: list) -> list:
    """Names appearing on more than one entry, case-insensitively.

    A ledger merged from several extraction runs accumulates these
    ("Salesforce CRM" four times), and they are the main thing a
    maintenance pass is here to clean up.
    """
    counts: dict = {}
    for t in tools:
        key = (t.get("name") or "").strip().lower()
        if key:
            counts[key] = counts.get(key, 0) + 1
    return sorted(n for n, c in counts.items() if c > 1)


def _display_skills_dashboard(tools: list):
    """A one-screen summary, never the whole ledger.

    Printing every entry (1,400+ on a real profile) pushed the action menu
    off the bottom of the terminal and buried it in scrollback; the full
    list belongs in the pickers below, which filter and paginate.
    """
    categories = _by_category(tools)
    dupes = _duplicate_names(tools)

    cli_art.console.print("[bold cyan]Active Skills Inventory[/bold cyan]")
    summary = (
        f"[green]{len(tools)}[/green] verified tool(s)/skill(s) across "
        f"[green]{len(categories)}[/green] categor(ies)"
    )
    if dupes:
        summary += f", [yellow]{len(dupes)}[/yellow] duplicated name(s)"
    cli_art.console.print(summary)

    for cat, items in sorted(categories.items()):
        cli_art.console.print(
            f"  [bold yellow]▪ {cat}[/bold yellow] [dim]— {len(items)}[/dim]"
        )
    if dupes:
        shown = ", ".join(dupes[:5]) + (" …" if len(dupes) > 5 else "")
        cli_art.console.print(
            f"  [dim]Duplicates: {shown} — use Remove Skills in Bulk to clean up.[/dim]"
        )
    cli_art.console.print()


def _add_skill(data: dict):
    tools = data.setdefault("tools", [])

    name = cli_art.text("Skill/Tool Name (e.g. Asana, ChatGPT):")
    if not name or not name.strip():
        return
    name = name.strip()

    # Suggest existing categories -- shown inline since cli_art/charm_prompt
    # has no autocomplete primitive (questionary.autocomplete() has no Go/huh
    # counterpart the way select/checkbox/text/confirm/password do).
    existing_categories = sorted(
        list({t.get("category", "") for t in tools if t.get("category")})
    )
    category_hint = (
        f" (existing: {', '.join(existing_categories)})" if existing_categories else ""
    )
    category = cli_art.text(f"Category{category_hint}:")
    if not category or not category.strip():
        return
    category = category.strip()

    confidence = cli_art.select(
        "Confidence/Fluency level:",
        choices=["Expert", "Advanced", "Proficient", "Working Knowledge", "Familiar"],
    )
    if not confidence:
        return

    evidence_count_str = cli_art.text(
        "Evidence Count (number of projects/roles using this):", default="1"
    )
    if evidence_count_str is None:
        cli_art.console.print(
            f"{cli_art.WARNING} Skill creation cancelled.", soft_wrap=True
        )
        return

    try:
        evidence_count = int(evidence_count_str)
    except ValueError:
        evidence_count = 1

    use_notes = cli_art.text("Use Notes (how you have used this skill/tool):")
    if use_notes is None:
        cli_art.console.print(
            f"{cli_art.WARNING} Skill creation cancelled.", soft_wrap=True
        )
        return
    use_notes = use_notes.strip()

    tr_references_str = cli_art.text(
        "Evidence/Project References (comma-separated, e.g. TR-0007, profile.yml):",
        default="profile.yml",
    )
    if tr_references_str is None:
        cli_art.console.print(
            f"{cli_art.WARNING} Skill creation cancelled.", soft_wrap=True
        )
        return
    tr_references = [r.strip() for r in tr_references_str.split(",") if r.strip()]

    new_tool = {
        "id": _generate_next_id(tools),
        "name": name,
        "category": category,
        "confidence": confidence,
        "evidence_count": evidence_count,
        "use_notes": use_notes,
        "tr_references": tr_references,
    }

    tools.append(new_tool)
    if _save_verified_tools(data):
        cli_art.display_success(f"Successfully added skill: '{name}'")
        _pause()


def _edit_skill(data: dict, tool_id: str):
    tools = data.get("tools", [])
    tool = next((t for t in tools if t.get("id") == tool_id), None)
    if not tool:
        cli_art.display_error("Skill not found.")
        return

    cli_art.console.print(
        f"\n[bold cyan]Editing Skill: {tool.get('name')}[/bold cyan]\n"
    )

    name = cli_art.text("Skill/Tool Name:", default=tool.get("name", ""))
    if not name or not name.strip():
        return

    existing_categories = sorted(
        list({t.get("category", "") for t in tools if t.get("category")})
    )
    category_hint = (
        f" (existing: {', '.join(existing_categories)})" if existing_categories else ""
    )
    category = cli_art.text(
        f"Category{category_hint}:", default=tool.get("category", "")
    )
    if not category or not category.strip():
        return

    confidence = cli_art.select(
        "Confidence/Fluency level:",
        choices=["Expert", "Advanced", "Proficient", "Working Knowledge", "Familiar"],
        default=tool.get("confidence", "Proficient"),
    )
    if not confidence:
        return

    evidence_count_str = cli_art.text(
        "Evidence Count:", default=str(tool.get("evidence_count", 1))
    )
    if evidence_count_str is None:
        cli_art.console.print(
            f"{cli_art.WARNING} Skill edit cancelled.", soft_wrap=True
        )
        return
    try:
        evidence_count = int(evidence_count_str)
    except ValueError:
        evidence_count = tool.get("evidence_count", 1)

    use_notes = cli_art.text("Use Notes:", default=tool.get("use_notes", ""))
    if use_notes is None:
        cli_art.console.print(
            f"{cli_art.WARNING} Skill edit cancelled.", soft_wrap=True
        )
        return

    refs_default = ", ".join(tool.get("tr_references", []))
    tr_references_str = cli_art.text(
        "Evidence/Project References (comma-separated):", default=refs_default
    )
    if tr_references_str is None:
        cli_art.console.print(
            f"{cli_art.WARNING} Skill edit cancelled.", soft_wrap=True
        )
        return
    tr_references = [r.strip() for r in tr_references_str.split(",") if r.strip()]

    tool["name"] = name.strip()
    tool["category"] = category.strip()
    tool["confidence"] = confidence
    tool["evidence_count"] = evidence_count
    tool["use_notes"] = use_notes.strip()
    tool["tr_references"] = tr_references

    if _save_verified_tools(data):
        cli_art.display_success(f"Successfully updated skill: '{name.strip()}'")
        _pause()


def _delete_skill(data: dict, tool_id: str):
    tools = data.get("tools", [])
    tool = next((t for t in tools if t.get("id") == tool_id), None)
    if not tool:
        cli_art.display_error("Skill not found.")
        return

    confirm = cli_art.confirm(
        f"Are you sure you want to delete the skill '{tool.get('name')}'?",
        default=False,
    )
    if confirm:
        data["tools"] = [t for t in tools if t.get("id") != tool_id]
        if _save_verified_tools(data):
            cli_art.display_success(f"Successfully deleted skill: '{tool.get('name')}'")
            _pause()


def _skill_label(tool: dict, dupes: set) -> str:
    """One picker row. `⧉` marks a name the ledger holds more than once,
    which is what makes a cleanup pass possible without opening each entry."""
    mark = "⧉ " if (tool.get("name") or "").strip().lower() in dupes else ""
    return (
        f"{mark}[{tool.get('category') or 'Uncategorized'}] "
        f"{tool.get('name')} ({tool.get('confidence')})"
    )


def _sorted_tools(tools: list) -> list:
    return sorted(
        tools,
        key=lambda x: ((x.get("category") or ""), (x.get("name") or "").lower()),
    )


def _bulk_remove_skills(data: dict):
    """Deletes several ledger entries in one pass, on the same grid the
    Skill Gap Scan uses -- removing merge duplicates one at a time through
    the details screen is what made them accumulate."""
    tools = data.get("tools", [])
    if not tools:
        cli_art.detail("No skills to remove yet.", level=cli_art.NORMAL)
        _pause()
        return

    dupes = set(_duplicate_names(tools))
    cli_art.detail(
        f"{len(tools)} skill(s); ⧉ marks a name that appears more than once. "
        "Click or press space to toggle, a to select/deselect everything "
        "shown, / to filter.",
        level=cli_art.NORMAL,
    )
    choices = [
        questionary.Choice(_skill_label(t, dupes), t.get("id"))
        for t in _sorted_tools(tools)
    ]
    selected = cli_art.checkbox(
        "Select skills/tools to remove from your verified ledger:",
        choices=choices,
        grid=True,
    )
    if not selected:
        return

    names = [
        t.get("name") for t in tools if t.get("id") in set(selected) and t.get("name")
    ]
    if not cli_art.confirm(
        f"Permanently remove {len(selected)} skill(s)? "
        f"({', '.join(names[:5])}{' …' if len(names) > 5 else ''})",
        default=False,
    ):
        cli_art.detail("Cancelled -- no changes made.", level=cli_art.NORMAL)
        _pause()
        return

    data["tools"] = [t for t in tools if t.get("id") not in set(selected)]
    if _save_verified_tools(data):
        cli_art.display_success(f"Removed {len(selected)} skill(s) from the ledger.")
        _pause()


def _view_skill_details(data: dict, tool_id: str):
    tools = data.get("tools", [])
    tool = next((t for t in tools if t.get("id") == tool_id), None)
    if not tool:
        cli_art.display_error("Skill not found.")
        return

    while True:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
        cli_art.display_compact_banner(
            f"SKILL DETAILS | {(tool.get('name') or 'Unnamed').upper()}"
        )
        cli_art.display_footer_commands()
        cli_art.console.print()

        cli_art.console.print(
            f"[bold cyan]Skill/Tool Name:[/bold cyan] {tool.get('name')}"
        )
        cli_art.console.print(
            f"[bold cyan]Category:[/bold cyan]        {tool.get('category')}"
        )
        cli_art.console.print(
            f"[bold cyan]Fluency/Confidence:[/bold cyan] {tool.get('confidence')}"
        )
        cli_art.console.print(
            f"[bold cyan]Evidence Count:[/bold cyan]     {tool.get('evidence_count')}"
        )
        cli_art.console.print(
            f"[bold cyan]References:[/bold cyan]         {', '.join(tool.get('tr_references', []))}"
        )
        cli_art.console.print(
            f"[bold cyan]Use Notes:[/bold cyan]\n  {tool.get('use_notes')}\n"
        )

        choices = [
            questionary.Choice("✏  Edit This Skill", "edit"),
            questionary.Choice("✗  Delete This Skill", "delete"),
            questionary.Choice("⬅  Back to Skills List", "back"),
        ]

        action = cli_art.select("Manage This Skill", choices=choices)
        if not action or action == "back":
            break
        if action == "edit":
            _edit_skill(data, tool_id)
            # Reload updated data
            data = _load_verified_tools()
            tool = next(
                (t for t in data.get("tools", []) if t.get("id") == tool_id), None
            )
            if not tool:
                break
        if action == "delete":
            _delete_skill(data, tool_id)
            break


def run_skills_menu():
    """Renders the main Skills & Tools management screen loop."""
    import menu

    use_alt = menu._should_use_alt_screen()

    while True:
        if use_alt:
            sys.stdout.write("\x1b[2J\x1b[H")
            sys.stdout.flush()
            cli_art.display_compact_banner("PROFILE SKILLS MANAGEMENT")
            cli_art.display_footer_commands()
            cli_art.console.print()

        data = _load_verified_tools()
        tools = data.get("tools", [])

        _display_skills_dashboard(tools)

        choices = [
            charm_prompt.Heading("Skills & Tools"),
            questionary.Choice("➕  Add New Skill/Tool", "add_skill"),
        ]
        if tools:
            choices.append(
                questionary.Choice(
                    "◉  Select a Skill to View/Edit/Delete", "select_skill"
                )
            )
            choices.append(
                questionary.Choice("✗  Remove Skills in Bulk", "bulk_remove")
            )
        choices += [
            charm_prompt.Heading("Career Facts"),
            questionary.Choice(
                "★  Review Staged Career Facts (D10 Gate)", "review_staged_facts"
            ),
            questionary.Choice("📜  View Verified Facts Ledger", "view_facts_ledger"),
            charm_prompt.Heading("Maintenance"),
            questionary.Choice(
                "🚫  Manage Dismissed Skills (Not My Background)", "manage_dismissed"
            ),
            questionary.Choice("⬅  Back to Settings & Upkeep", "back"),
        ]

        action = cli_art.select("Skills Actions", choices=choices)
        if not action or action == "back":
            break

        if action == "add_skill":
            _add_skill(data)
            continue

        if action == "review_staged_facts":
            import facts_manager

            facts_manager.review_staged_facts_interactive()
            continue

        if action == "view_facts_ledger":
            import facts_manager

            facts_manager.display_facts_inventory()
            cli_art.text("Press Enter to return to Skills & Facts menu...")
            continue

        if action == "manage_dismissed":
            _manage_dismissed_skills()
            continue

        if action == "bulk_remove":
            _bulk_remove_skills(data)
            continue

        if action == "select_skill":
            # Grouped under category headings, the same shape as this menu --
            # a flat 1,400-row list is unusable without them.
            dupes = set(_duplicate_names(tools))
            skill_choices = []
            current_cat = None
            for t in _sorted_tools(tools):
                cat = t.get("category") or "Uncategorized"
                if cat != current_cat:
                    current_cat = cat
                    skill_choices.append(charm_prompt.Heading(cat))
                name = t.get("name")
                mark = "⧉ " if (name or "").strip().lower() in dupes else ""
                skill_choices.append(
                    questionary.Choice(
                        f"{mark}{name} ({t.get('confidence')})", t.get("id")
                    )
                )
            skill_choices.append(charm_prompt.Heading("  "))
            skill_choices.append(questionary.Choice("⬅  Cancel", "back"))

            selected_id = cli_art.select(
                "Select a skill to manage:", choices=skill_choices
            )
            if selected_id and selected_id != "back":
                _view_skill_details(data, selected_id)
            continue
