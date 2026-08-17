"""
skills_menu.py -- Interactive profile skills / verified tools editor.
Allows users to add, edit, and delete tools/skills stored under
verified_tools.json in their active profile's knowledge base.
"""

import json
import os
import sys
import questionary

import profile_paths
import theme
import cli_art
from atomic_write import atomic_write


def _get_verified_tools_path() -> str:
    kb_dir = profile_paths.kb_dir()
    return os.path.join(kb_dir, "verified_tools.json")


def _load_verified_tools() -> dict:
    path = _get_verified_tools_path()
    if not os.path.exists(path):
        return {"_meta": {"source": "manual", "last_updated": "", "total_entries": 0, "note": "Confidence reflects depth of documented use in archive evidence."}, "tools": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        cli_art.display_error(f"Failed to read verified_tools.json: {e}")
        return {"_meta": {"source": "manual", "last_updated": "", "total_entries": 0, "note": "Confidence reflects depth of documented use in archive evidence."}, "tools": []}


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
        return False


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


def _display_skills_dashboard(tools: list):
    cli_art.console.print("[bold cyan]Active Skills Inventory[/bold cyan]")
    cli_art.console.print(f"Total Verified Tools/Skills: [green]{len(tools)}[/green]\n")
    
    # Display table of skills grouped by category
    categories = {}
    for t in tools:
        cat = t.get("category", "Uncategorized")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(t)
        
    for cat, items in sorted(categories.items()):
        cli_art.console.print(f"[bold yellow]▪ {cat}[/bold yellow]")
        for item in sorted(items, key=lambda x: x.get("name", "")):
            cli_art.console.print(f"  - [white]{item.get('name')}[/white] ([cyan]{item.get('confidence')}[/cyan])")
    cli_art.console.print()


def _add_skill(data: dict):
    tools = data.setdefault("tools", [])
    
    name = questionary.text("Skill/Tool Name (e.g. Asana, ChatGPT):").ask()
    if not name or not name.strip():
        return
    name = name.strip()
    
    # Suggest existing categories
    existing_categories = sorted(list({t.get("category", "") for t in tools if t.get("category")}))
    category = questionary.autocomplete(
        "Category:",
        choices=existing_categories,
        validate=lambda x: len(x.strip()) > 0 or "Category cannot be empty."
    ).ask()
    if not category:
        return
    category = category.strip()
    
    confidence = questionary.select(
        "Confidence/Fluency level:",
        choices=["Expert", "Advanced", "Proficient", "Working Knowledge", "Familiar"]
    ).ask()
    if not confidence:
        return
        
    evidence_count_str = questionary.text("Evidence Count (number of projects/roles using this):", default="1").ask()
    if evidence_count_str is None:
        cli_art.console.print(f"{cli_art.WARNING} Skill creation cancelled.", soft_wrap=True)
        return

    try:
        evidence_count = int(evidence_count_str)
    except ValueError:
        evidence_count = 1
        
    use_notes = questionary.text("Use Notes (how you have used this skill/tool):").ask()
    if use_notes is None:
        cli_art.console.print(f"{cli_art.WARNING} Skill creation cancelled.", soft_wrap=True)
        return
    use_notes = use_notes.strip()
    
    tr_references_str = questionary.text("Evidence/Project References (comma-separated, e.g. TR-0007, profile.yml):", default="profile.yml").ask()
    if tr_references_str is None:
        cli_art.console.print(f"{cli_art.WARNING} Skill creation cancelled.", soft_wrap=True)
        return
    tr_references = [r.strip() for r in tr_references_str.split(",") if r.strip()]
    
    new_tool = {
        "id": _generate_next_id(tools),
        "name": name,
        "category": category,
        "confidence": confidence,
        "evidence_count": evidence_count,
        "use_notes": use_notes,
        "tr_references": tr_references
    }
    
    tools.append(new_tool)
    if _save_verified_tools(data):
        cli_art.display_success(f"Successfully added skill: '{name}'")


def _edit_skill(data: dict, tool_id: str):
    tools = data.get("tools", [])
    tool = next((t for t in tools if t.get("id") == tool_id), None)
    if not tool:
        cli_art.display_error("Skill not found.")
        return
        
    cli_art.console.print(f"\n[bold cyan]Editing Skill: {tool.get('name')}[/bold cyan]\n")
    
    name = questionary.text("Skill/Tool Name:", default=tool.get("name", "")).ask()
    if not name or not name.strip():
        return
    
    existing_categories = sorted(list({t.get("category", "") for t in tools if t.get("category")}))
    category = questionary.autocomplete(
        "Category:",
        choices=existing_categories,
        default=tool.get("category", "")
    ).ask()
    if not category:
        return
        
    confidence = questionary.select(
        "Confidence/Fluency level:",
        choices=["Expert", "Advanced", "Proficient", "Working Knowledge", "Familiar"],
        default=tool.get("confidence", "Proficient")
    ).ask()
    if not confidence:
        return
        
    evidence_count_str = questionary.text("Evidence Count:", default=str(tool.get("evidence_count", 1))).ask()
    try:
        evidence_count = int(evidence_count_str)
    except ValueError:
        evidence_count = tool.get("evidence_count", 1)
        
    use_notes = questionary.text("Use Notes:", default=tool.get("use_notes", "")).ask()
    
    refs_default = ", ".join(tool.get("tr_references", []))
    tr_references_str = questionary.text("Evidence/Project References (comma-separated):", default=refs_default).ask()
    tr_references = [r.strip() for r in (tr_references_str or "").split(",") if r.strip()]
    
    tool["name"] = name.strip()
    tool["category"] = category.strip()
    tool["confidence"] = confidence
    tool["evidence_count"] = evidence_count
    tool["use_notes"] = use_notes.strip()
    tool["tr_references"] = tr_references
    
    if _save_verified_tools(data):
        cli_art.display_success(f"Successfully updated skill: '{name.strip()}'")


def _delete_skill(data: dict, tool_id: str):
    tools = data.get("tools", [])
    tool = next((t for t in tools if t.get("id") == tool_id), None)
    if not tool:
        cli_art.display_error("Skill not found.")
        return
        
    confirm = cli_art.confirm(f"Are you sure you want to delete the skill '{tool.get('name')}'?", default=False)
    if confirm:
        data["tools"] = [t for t in tools if t.get("id") != tool_id]
        if _save_verified_tools(data):
            cli_art.display_success(f"Successfully deleted skill: '{tool.get('name')}'")


def _view_skill_details(data: dict, tool_id: str):
    tools = data.get("tools", [])
    tool = next((t for t in tools if t.get("id") == tool_id), None)
    if not tool:
        cli_art.display_error("Skill not found.")
        return
        
    while True:
        sys.stdout.write("\x1b[2J\x1b[H")
        sys.stdout.flush()
        cli_art.display_compact_banner(f"SKILL DETAILS | {tool.get('name').upper()}")
        cli_art.display_footer_commands()
        cli_art.console.print()
        
        cli_art.console.print(f"[bold cyan]Skill/Tool Name:[/bold cyan] {tool.get('name')}")
        cli_art.console.print(f"[bold cyan]Category:[/bold cyan]        {tool.get('category')}")
        cli_art.console.print(f"[bold cyan]Fluency/Confidence:[/bold cyan] {tool.get('confidence')}")
        cli_art.console.print(f"[bold cyan]Evidence Count:[/bold cyan]     {tool.get('evidence_count')}")
        cli_art.console.print(f"[bold cyan]References:[/bold cyan]         {', '.join(tool.get('tr_references', []))}")
        cli_art.console.print(f"[bold cyan]Use Notes:[/bold cyan]\n  {tool.get('use_notes')}\n")
        
        choices = [
            questionary.Choice("✏️  Edit This Skill", "edit"),
            questionary.Choice("❌  Delete This Skill", "delete"),
            questionary.Choice("⬅️  Back to Skills List", "back")
        ]
        
        action = cli_art.select("Manage This Skill", choices=choices)
        if not action or action == "back":
            break
        if action == "edit":
            _edit_skill(data, tool_id)
            # Reload updated data
            data = _load_verified_tools()
            tool = next((t for t in data.get("tools", []) if t.get("id") == tool_id), None)
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
            questionary.Choice("➕  Add New Skill/Tool", "add_skill"),
        ]
        if tools:
            choices.append(questionary.Choice("👁️  Select a Skill to View/Edit/Delete", "select_skill"))
        choices.append(questionary.Choice("⬅️  Back to Settings & Upkeep", "back"))
        
        action = cli_art.select("Skills Actions", choices=choices)
        if not action or action == "back":
            break
            
        if action == "add_skill":
            _add_skill(data)
            continue
            
        if action == "select_skill":
            # Build list of skills for selection
            skill_choices = []
            for t in sorted(tools, key=lambda x: (x.get("category", ""), x.get("name", "").lower())):
                label = f"[{t.get('category')}] {t.get('name')} ({t.get('confidence')})"
                skill_choices.append(questionary.Choice(label, t.get("id")))
            skill_choices.append(questionary.Choice("Cancel", "back"))
            
            selected_id = cli_art.select("Select a skill to manage:", choices=skill_choices)
            if selected_id and selected_id != "back":
                _view_skill_details(data, selected_id)
            continue
