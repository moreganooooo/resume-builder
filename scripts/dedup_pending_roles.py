"""dedup_pending_roles.py -- safely merges and archives duplicate pending jobs."""

import json
import os
import re
import sqlite3
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import db
import jd_manager


def normalize_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def get_job_url(meta: dict) -> str:
    u = (
        (meta.get("source_url") or meta.get("url") or meta.get("application_url") or "")
        .strip()
        .lower()
    )
    if any(
        g in u
        for g in (
            "tally.so",
            "google.com",
            "forms.gle",
            "airtable.com",
            "typeform.com",
            "boards.greenhouse.io/embed/job_app",
            "jobs.lever.co",
        )
    ):
        return ""
    if "?" in u:
        u = u.split("?")[0]
    return u.rstrip("/")


def run_deduplication(profile: str = None, dry_run: bool = True) -> dict:
    conn = db.get_db(profile)
    conn.row_factory = sqlite3.Row

    db_rows = conn.execute("SELECT * FROM jobs WHERE status = 'pending'").fetchall()
    pending_file_paths = jd_manager.get_pending_jds()

    items = {}
    for r in db_rows:
        meta = json.loads(r["metadata_json"] or "{}")
        eval_data = meta.get("_evaluation") or {}
        score = r["final_score"] or eval_data.get("composite_score") or 0.0
        u = get_job_url(meta)
        c_norm = normalize_text(r["company"])
        t_norm = normalize_text(r["title"])
        items[r["id"]] = {
            "id": r["id"],
            "row": r,
            "is_file": False,
            "file_path": None,
            "title": r["title"],
            "company": r["company"],
            "location": r["location"] or "",
            "dedup_hash": r["dedup_hash"] or "",
            "score": score,
            "url": u,
            "norm_tc": (c_norm, t_norm),
            "norm_tcl": (c_norm, t_norm, normalize_text(r["location"])),
            "meta": meta,
            "created_at": r["created_at"] or "",
        }

    for p in pending_file_paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                f_data = json.load(f)
            u = get_job_url(f_data)
            c = f_data.get("company_name") or f_data.get("company") or ""
            t = f_data.get("job_title") or f_data.get("title") or ""
            eval_data = f_data.get("_evaluation") or {}
            score = eval_data.get("composite_score") or 0.0
            c_norm = normalize_text(c)
            t_norm = normalize_text(t)
            items[p] = {
                "id": p,
                "row": None,
                "is_file": True,
                "file_path": p,
                "title": t,
                "company": c,
                "location": f_data.get("location") or "",
                "dedup_hash": f_data.get("dedup_hash") or jd_manager.compute_job_key(p),
                "score": score,
                "url": u,
                "norm_tc": (c_norm, t_norm),
                "norm_tcl": (c_norm, t_norm, normalize_text(f_data.get("location"))),
                "meta": f_data,
                "created_at": "",
            }
        except Exception:
            pass

    # Union-Find
    parent = {i: i for i in items}

    def find(i):
        if parent[i] != i:
            parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    # 1. Union by dedup_hash
    by_hash = {}
    for i, it in items.items():
        h = it["dedup_hash"]
        if h:
            by_hash.setdefault(h, []).append(i)
    for h, ids in by_hash.items():
        for o in ids[1:]:
            union(ids[0], o)

    # 2. Union by (source URL, normalized company). URL alone is not safe:
    # some ATS platforms (observed: ADP Workforce Now) route every posting
    # through the exact same generic recruitment-shell URL regardless of
    # employer or role, so keying on URL alone unioned four unrelated jobs
    # from four different companies into a single "duplicate" cluster.
    # Pairing with company matches job_key_known()'s existing convention
    # for the same reason (see its docstring).
    by_url = {}
    for i, it in items.items():
        u = it["url"]
        c_norm = it["norm_tc"][0]
        if u and len(u) > 15 and c_norm:
            by_url.setdefault((u, c_norm), []).append(i)
    for key, ids in by_url.items():
        for o in ids[1:]:
            union(ids[0], o)

    # 3. Union by exact normalized company + title
    by_tc = {}
    for i, it in items.items():
        c, t = it["norm_tc"]
        if c and t:
            by_tc.setdefault((c, t), []).append(i)
    for ids in by_tc.values():
        for o in ids[1:]:
            union(ids[0], o)

    # Group into clusters
    clusters = {}
    for i in items:
        root = find(i)
        clusters.setdefault(root, []).append(i)

    multi_clusters = {k: v for k, v in clusters.items() if len(v) > 1}

    archived_count = 0
    updated_winners = 0
    sample_clusters = []

    cursor = conn.cursor()

    for member_ids in multi_clusters.values():
        # Rank candidates:
        # 1. is_file (True first)
        # 2. score (highest first)
        # 3. richness of metadata (keys count)
        # 4. created_at (most recent first)
        sorted_members = sorted(
            member_ids,
            key=lambda cid: (
                1 if items[cid]["is_file"] else 0,
                items[cid]["score"],
                len(items[cid]["meta"]),
                items[cid]["created_at"],
            ),
            reverse=True,
        )

        winner_id = sorted_members[0]
        losers = sorted_members[1:]
        winner_item = items[winner_id]
        winner_meta = dict(winner_item["meta"])

        sample_clusters.append(
            {
                "winner": f"{winner_item['company']} -- {winner_item['title']}",
                "losers": [
                    f"{items[lid]['company']} -- {items[lid]['title']}"
                    for lid in losers
                ],
            }
        )

        if dry_run:
            continue

        # Merge metadata from losers into winner
        for loser_id in losers:
            loser_meta = items[loser_id]["meta"]
            for key in (
                "_location_enrichment",
                "_liveness",
                "_research",
                "_coverage",
                "source_url",
                "application_url",
                "company_website",
                "skills",
                "salary_min",
                "salary_max",
            ):
                if loser_meta.get(key) and not winner_meta.get(key):
                    winner_meta[key] = loser_meta[key]

        # Update winner if it's a DB row
        if not winner_item["is_file"]:
            if winner_meta != winner_item["meta"]:
                cursor.execute(
                    "UPDATE jobs SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (json.dumps(winner_meta), winner_id),
                )
                updated_winners += 1
        else:
            # Winner is a file -- update file on disk if missing fields merged
            if winner_meta != winner_item["meta"]:
                try:
                    with open(winner_id, "w", encoding="utf-8") as f:
                        json.dump(winner_meta, f, indent=2, ensure_ascii=False)
                    updated_winners += 1
                except Exception as e:
                    print(f"Warning: could not update winner file {winner_id}: {e}")

        # Archive losers
        for loser_id in losers:
            loser_item = items[loser_id]
            loser_meta = dict(loser_item["meta"])
            loser_meta["archived_reason"] = "duplicate"
            loser_meta["canonical_job_id"] = winner_id

            if not loser_item["is_file"]:
                # DB row
                cursor.execute(
                    "UPDATE jobs SET status = 'archived', metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (json.dumps(loser_meta), loser_id),
                )
                archived_count += 1
            else:
                # File row
                if loser_item["file_path"] and os.path.exists(loser_item["file_path"]):
                    try:
                        jd_manager.archive_jd(loser_item["file_path"])
                        archived_count += 1
                    except Exception as e:
                        print(
                            f"Warning: could not archive file {loser_item['file_path']}: {e}"
                        )

    if dry_run:
        conn.close()
    else:
        conn.commit()
        conn.close()
        db.checkpoint(profile)

    return {
        "total_clusters": len(multi_clusters),
        "total_archived_duplicates": archived_count,
        "updated_winners": updated_winners,
        "dry_run": dry_run,
        "sample_clusters": sample_clusters,
    }


if __name__ == "__main__":
    result = run_deduplication(dry_run=True)
    print(f"Dry run: {result['total_clusters']} duplicate clusters found.")
    for cluster in result["sample_clusters"][:10]:
        print(f"  KEEP: {cluster['winner']}")
        for loser in cluster["losers"]:
            print(f"    ARCHIVE: {loser}")
    print(
        "\nPass dry_run=False (or `resume dedupe --apply`) to actually archive these."
    )
