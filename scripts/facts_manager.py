"""
facts_manager.py — D10 Human-in-the-loop staged_facts.json gate.

Protects the candidate's canonical verified facts ledger (verified_facts.json)
from silent data loss, automated overwrite, or hallucination contamination.

All newly extracted or synthesized career claims are routed through staged_facts.json
and must be explicitly accepted, edited, or rejected by a human operator before
promotion into verified_facts.json.
"""

import datetime
import json
import os
import re
from typing import Any, Dict, List, Optional

import cli_art
import profile_paths
import questionary
import theme
from atomic_write import atomic_write


def get_verified_facts_path(profile: Optional[str] = None) -> str:
    """Returns the absolute path to verified_facts.json for the active or given profile."""
    kb_dir = profile_paths.kb_dir(profile=profile)
    return os.path.join(kb_dir, "verified_facts.json")


def get_staged_facts_path(profile: Optional[str] = None) -> str:
    """Returns the absolute path to staged_facts.json for the active or given profile."""
    kb_dir = profile_paths.kb_dir(profile=profile)
    return os.path.join(kb_dir, "staged_facts.json")


def load_verified_facts(profile: Optional[str] = None) -> Dict[str, Any]:
    """Loads verified_facts.json safely.

    Raises an exception on JSON parsing or I/O corruption rather than returning
    an empty skeleton, preventing transient read errors from causing permanent
    data loss on subsequent writes.
    """
    path = get_verified_facts_path(profile=profile)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return {
            "_meta": {
                "source": "manual",
                "last_updated": "",
                "total_entries": 0,
                "note": "Verified claims about achievements and initiatives.",
            },
            "facts": [],
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"Root of {path} must be a JSON object")
            if "facts" not in data or not isinstance(data["facts"], list):
                data["facts"] = []
            return data
    except Exception as e:
        cli_art.cli_error(
            f"Failed to read verified_facts.json at {path}: {e}. "
            "Refusing to fall back to an empty skeleton to prevent data loss."
        )
        raise


def save_verified_facts(data: Dict[str, Any], profile: Optional[str] = None) -> bool:
    """Atomically saves verified_facts.json and updates metadata counters."""
    path = get_verified_facts_path(profile=profile)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if "_meta" not in data or not isinstance(data["_meta"], dict):
            data["_meta"] = {}
        data["_meta"]["total_entries"] = len(data.get("facts", []))
        data["_meta"]["last_updated"] = datetime.date.today().isoformat()

        with atomic_write(path, encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        cli_art.cli_error(f"Failed to save verified_facts.json at {path}: {e}")
        return False


def load_staged_facts(profile: Optional[str] = None) -> Dict[str, Any]:
    """Loads staged_facts.json safely.

    Candidate facts staged here await human verification before being committed
    to verified_facts.json.
    """
    path = get_staged_facts_path(profile=profile)
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return {
            "_meta": {
                "source": "staged_extraction",
                "last_updated": "",
                "total_entries": 0,
                "note": "Candidate facts awaiting human review before promotion to verified_facts.json (D10 gate).",
            },
            "staged_facts": [],
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(f"Root of {path} must be a JSON object")
            if "staged_facts" not in data or not isinstance(data["staged_facts"], list):
                data["staged_facts"] = []
            return data
    except Exception as e:
        cli_art.cli_error(
            f"Failed to read staged_facts.json at {path}: {e}. "
            "Refusing to fall back to an empty skeleton."
        )
        raise


def save_staged_facts(data: Dict[str, Any], profile: Optional[str] = None) -> bool:
    """Atomically saves staged_facts.json and updates metadata counters."""
    path = get_staged_facts_path(profile=profile)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if "_meta" not in data or not isinstance(data["_meta"], dict):
            data["_meta"] = {}
        data["_meta"]["total_entries"] = len(data.get("staged_facts", []))
        data["_meta"]["last_updated"] = datetime.date.today().isoformat()

        with atomic_write(path, encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        cli_art.cli_error(f"Failed to save staged_facts.json at {path}: {e}")
        return False


def _normalize_key(label: str, claim: str) -> str:
    """Case- and punctuation-insensitive normalization for deduplication."""
    joined = f"{(label or '').strip()} {(claim or '').strip()}".lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", joined).split())


def _generate_next_verified_id(facts: List[Dict[str, Any]]) -> str:
    """Generates next fact_XXX identifier (e.g. fact_019)."""
    highest = 0
    for f in facts:
        fid = f.get("id", "")
        if fid.startswith("fact_"):
            try:
                num = int(fid.split("_")[1])
                highest = max(highest, num)
            except (ValueError, IndexError):
                pass
    return f"fact_{highest + 1:03d}"


def _generate_next_staged_id(staged_facts: List[Dict[str, Any]]) -> str:
    """Generates next staged_fact_XXX identifier."""
    highest = 0
    for sf in staged_facts:
        sfid = sf.get("id", "")
        if sfid.startswith("staged_fact_"):
            try:
                num = int(sfid.split("_")[2])
                highest = max(highest, num)
            except (ValueError, IndexError):
                pass
    return f"staged_fact_{highest + 1:03d}"


def stage_facts(
    candidate_facts: List[Dict[str, Any]],
    profile: Optional[str] = None,
    source: str = "ai_extraction",
) -> int:
    """Stages candidate facts into staged_facts.json.

    Deduplicates against both existing verified_facts.json and existing
    staged_facts.json. Never modifies or overwrites verified_facts.json.

    Returns the count of newly staged facts.
    """
    if not candidate_facts:
        return 0

    verified_data = load_verified_facts(profile=profile)
    staged_data = load_staged_facts(profile=profile)

    seen_keys = set()
    for f in verified_data.get("facts", []):
        seen_keys.add(_normalize_key(f.get("label", ""), f.get("claim", "")))
    for sf in staged_data.get("staged_facts", []):
        seen_keys.add(_normalize_key(sf.get("label", ""), sf.get("claim", "")))

    now = datetime.datetime.now().isoformat(timespec="seconds")
    added_count = 0

    for cand in candidate_facts:
        label = cand.get("label", "").strip()
        claim = cand.get("claim", "").strip()
        if not label or not claim:
            continue

        key = _normalize_key(label, claim)
        if key in seen_keys:
            continue

        seen_keys.add(key)
        staged_id = _generate_next_staged_id(staged_data["staged_facts"])
        new_entry = {
            "id": staged_id,
            "label": label,
            "claim": claim,
            "source": cand.get("source", source),
            "confidence": cand.get("confidence", "High"),
            "use_in_resume": cand.get("use_in_resume", True),
            "caveat": cand.get("caveat", ""),
            "category": cand.get("category", "general"),
            "status": "staged",
            "staged_at": now,
        }
        staged_data["staged_facts"].append(new_entry)
        added_count += 1

    if added_count > 0:
        save_staged_facts(staged_data, profile=profile)

    return added_count


def promote_fact(
    staged_id: str,
    edited_fact: Optional[Dict[str, Any]] = None,
    profile: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Atomically promotes a staged fact from staged_facts.json into verified_facts.json.

    Generates a canonical fact_XXX ID, removes it from staged_facts.json, and
    saves both files atomically.
    """
    staged_data = load_staged_facts(profile=profile)
    verified_data = load_verified_facts(profile=profile)

    target_idx = None
    target_fact = None
    for idx, sf in enumerate(staged_data.get("staged_facts", [])):
        if sf.get("id") == staged_id:
            target_idx = idx
            target_fact = sf
            break

    if target_idx is None or target_fact is None:
        return None

    # Remove from staged
    staged_data["staged_facts"].pop(target_idx)

    # Base payload is either edited_fact or the original candidate
    promoted_payload = dict(edited_fact if edited_fact is not None else target_fact)
    # Strip staging-specific metadata
    promoted_payload.pop("staged_at", None)
    promoted_payload.pop("status", None)

    # Assign next official verified fact ID
    new_id = _generate_next_verified_id(verified_data.get("facts", []))
    promoted_payload["id"] = new_id

    # Append to verified facts
    verified_data["facts"].append(promoted_payload)

    # Save both files
    save_verified_facts(verified_data, profile=profile)
    save_staged_facts(staged_data, profile=profile)

    return promoted_payload


def reject_fact(staged_id: str, profile: Optional[str] = None) -> bool:
    """Discards a candidate fact from staged_facts.json without promoting it."""
    staged_data = load_staged_facts(profile=profile)
    target_idx = None
    for idx, sf in enumerate(staged_data.get("staged_facts", [])):
        if sf.get("id") == staged_id:
            target_idx = idx
            break

    if target_idx is None:
        return False

    staged_data["staged_facts"].pop(target_idx)
    return save_staged_facts(staged_data, profile=profile)


def promote_all_staged(profile: Optional[str] = None) -> int:
    """Promotes all currently staged facts to verified_facts.json."""
    staged_data = load_staged_facts(profile=profile)
    if not staged_data.get("staged_facts"):
        return 0

    verified_data = load_verified_facts(profile=profile)
    promoted_count = 0

    for sf in list(staged_data["staged_facts"]):
        payload = dict(sf)
        payload.pop("staged_at", None)
        payload.pop("status", None)
        payload["id"] = _generate_next_verified_id(verified_data["facts"])
        verified_data["facts"].append(payload)
        promoted_count += 1

    staged_data["staged_facts"] = []
    save_verified_facts(verified_data, profile=profile)
    save_staged_facts(staged_data, profile=profile)
    return promoted_count


def reject_all_staged(profile: Optional[str] = None) -> int:
    """Discards all currently staged facts."""
    staged_data = load_staged_facts(profile=profile)
    count = len(staged_data.get("staged_facts", []))
    staged_data["staged_facts"] = []
    save_staged_facts(staged_data, profile=profile)
    return count


def display_facts_inventory(profile: Optional[str] = None) -> None:
    """Renders a clean terminal summary of verified facts and pending staged claims."""
    verified_data = load_verified_facts(profile=profile)
    staged_data = load_staged_facts(profile=profile)

    facts = verified_data.get("facts", [])
    staged = staged_data.get("staged_facts", [])

    cli_art.console.print(
        f"[{theme.BRAND}]✦  CAREER FACTS LEDGER INVENTORY  ✦[/{theme.BRAND}]"
    )
    cli_art.console.print(
        f"Verified Facts: [green]{len(facts)}[/green] | "
        f"Staged Candidate Facts (Pending D10 Review): [{'yellow' if staged else 'dim'}]{len(staged)}[/{'yellow' if staged else 'dim'}]\n"
    )

    if facts:
        categories: Dict[str, List[Dict[str, Any]]] = {}
        for f in facts:
            cat = f.get("category", "general")
            categories.setdefault(cat, []).append(f)

        for cat, items in sorted(categories.items()):
            cli_art.console.print(f"[bold yellow]▪ {cat.upper()}[/bold yellow]")
            for item in items:
                cli_art.console.print(
                    f"  - [white]{item.get('label')}[/white] ([cyan]{item.get('id')}[/cyan])"
                )
                cli_art.console.print(f"    [dim]{item.get('claim')}[/dim]")
                if item.get("caveat"):
                    cli_art.console.print(
                        f"    [italic red]⚠ Caveat: {item.get('caveat')}[/italic red]"
                    )
        cli_art.console.print()


def review_staged_facts_interactive(profile: Optional[str] = None) -> Dict[str, int]:
    """Interactive human-in-the-loop review flow (D10 Gate).

    Presents candidate facts one by one, allowing the operator to Accept,
    Edit & Accept, Reject, or Skip each claim.
    """
    staged_data = load_staged_facts(profile=profile)
    staged_list = list(staged_data.get("staged_facts", []))

    tally = {"accepted": 0, "edited": 0, "rejected": 0, "skipped": 0}

    if not staged_list:
        cli_art.cli_info("No candidate facts are currently staged for review.")
        return tally

    cli_art.console.print()
    cli_art.console.print(
        f"[{theme.BRAND}]✦  HUMAN-IN-THE-LOOP FACT VERIFICATION (D10 GATE)  ✦[/{theme.BRAND}]"
    )
    cli_art.console.print(
        "Candidate claims extracted from documents or AI synthesis are staged below.\n"
        "Review each claim before promoting it to your verified ledger (verified_facts.json).\n"
    )

    for i, sf in enumerate(staged_list, start=1):
        cli_art.console.print(
            f"[bold cyan]── Claim {i} of {len(staged_list)}: {sf.get('label')} ──[/bold cyan]"
        )
        cli_art.console.print(f"[white][bold]Claim:[/bold] {sf.get('claim')}[/white]")
        if sf.get("source"):
            cli_art.console.print(f"[dim][bold]Source:[/bold] {sf.get('source')}[/dim]")
        if sf.get("caveat"):
            cli_art.console.print(
                f"[{theme.BRAND_ACCENT}][bold]Caveat:[/bold] {sf.get('caveat')}[/{theme.BRAND_ACCENT}]"
            )
        cli_art.console.print(
            f"[dim]Category: {sf.get('category', 'general')} | Confidence: {sf.get('confidence', 'High')}[/dim]\n"
        )

        try:
            choice = questionary.select(
                f"Action for '{sf.get('label')}':",
                choices=[
                    "✓ Accept & Verify (Promote to verified_facts.json)",
                    "✎ Edit & Accept (Refine claim text before promoting)",
                    "✗ Reject (Discard from staging)",
                    "⏭ Skip (Keep staged for later)",
                    "★ Accept All Remaining",
                    "⏹ Exit Review",
                ],
                style=cli_art.QUESTIONARY_STYLE,
            ).ask()
        except Exception:
            choice = "⏭ Skip (Keep staged for later)"

        if not choice or "Exit" in choice:
            cli_art.cli_info("Exited staged facts review.")
            break

        if "Accept All Remaining" in choice:
            promoted = promote_all_staged(profile=profile)
            tally["accepted"] += promoted
            cli_art.cli_info(
                f"Promoted all {promoted} remaining staged claims to verified_facts.json!"
            )
            break

        if "Accept & Verify" in choice:
            promoted = promote_fact(sf.get("id"), profile=profile)
            if promoted:
                tally["accepted"] += 1
                cli_art.cli_info(
                    f"Promoted '{promoted.get('label')}' as {promoted.get('id')}!"
                )

        elif "Edit & Accept" in choice:
            new_label = questionary.text(
                "Fact Label:",
                default=sf.get("label", ""),
                style=cli_art.QUESTIONARY_STYLE,
            ).ask() or sf.get("label", "")

            new_claim = questionary.text(
                "Fact Claim:",
                default=sf.get("claim", ""),
                style=cli_art.QUESTIONARY_STYLE,
            ).ask() or sf.get("claim", "")

            new_caveat = (
                questionary.text(
                    "Caveat / Scope Limits (optional):",
                    default=sf.get("caveat", ""),
                    style=cli_art.QUESTIONARY_STYLE,
                ).ask()
                or ""
            )

            new_category = (
                questionary.text(
                    "Category:",
                    default=sf.get("category", "general"),
                    style=cli_art.QUESTIONARY_STYLE,
                ).ask()
                or "general"
            )

            edited_payload = {
                "label": new_label.strip(),
                "claim": new_claim.strip(),
                "source": sf.get("source", ""),
                "confidence": sf.get("confidence", "High"),
                "use_in_resume": sf.get("use_in_resume", True),
                "caveat": new_caveat.strip(),
                "category": new_category.strip(),
            }

            promoted = promote_fact(
                sf.get("id"), edited_fact=edited_payload, profile=profile
            )
            if promoted:
                tally["edited"] += 1
                cli_art.cli_info(f"Promoted edited claim as {promoted.get('id')}!")

        elif "Reject" in choice:
            if reject_fact(sf.get("id"), profile=profile):
                tally["rejected"] += 1
                cli_art.cli_warning(f"Discarded candidate claim '{sf.get('label')}'.")

        elif "Skip" in choice:
            tally["skipped"] += 1

        cli_art.console.print()

    if tally["accepted"] > 0 or tally["edited"] > 0:
        cli_art.display_success_celebration(
            "CAREER FACTS VERIFIED",
            f"Successfully promoted {tally['accepted'] + tally['edited']} factual claims to verified_facts.json!",
        )

    return tally
