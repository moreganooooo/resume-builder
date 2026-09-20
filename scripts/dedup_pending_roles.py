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


def normalize_text(text: str | None) -> str:
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


def archive_copies_of(meta: dict, exclude_ids=(), profile: str | None = None) -> int:
    """Archives every PENDING data.db row that is another copy of the posting
    `meta` describes, by the same rules run_deduplication() clusters on --
    same dedup_hash, or same normalized company + title (which subsumes its
    URL + company + title rule). Returns how many rows it archived.

    Archiving a posting used to reach only the one record it was called on:
    a posting often has a file plus copies under other ids, so the copies
    stayed pending and the "archived" posting never left the list (16 rows
    for 12 postings, 2026-09-13). Only called from explicit archive actions
    -- never from jd_source.set_status() in general, since run_deduplication
    archives its losers through status writes and would archive its own
    winner."""
    c_norm = normalize_text(meta.get("company_name") or meta.get("company"))
    t_norm = normalize_text(meta.get("job_title") or meta.get("title"))
    h = str(meta.get("dedup_hash") or "")
    if not (c_norm and t_norm) and not h:
        return 0
    exclude = {str(x) for x in exclude_ids if x}
    conn = db.get_db(profile)
    conn.row_factory = sqlite3.Row
    archived = 0
    try:
        rows = conn.execute(
            "SELECT id, company, title, dedup_hash, metadata_json FROM jobs "
            "WHERE lower(status) = 'pending'"
        ).fetchall()
        for r in rows:
            if str(r["id"]) in exclude:
                continue
            same_hash = bool(h) and str(r["dedup_hash"] or "") == h
            same_posting = bool(c_norm and t_norm) and (
                normalize_text(r["company"]),
                normalize_text(r["title"]),
            ) == (c_norm, t_norm)
            if not (same_hash or same_posting):
                continue
            r_meta = json.loads(r["metadata_json"] or "{}")
            r_meta["archived_reason"] = "copy of an archived posting"
            conn.execute(
                "UPDATE jobs SET status = 'archived', metadata_json = ?, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(r_meta), r["id"]),
            )
            archived += 1
        conn.commit()
    finally:
        conn.close()
    return archived


def archive_copies_of_file(jd_path: str, profile: str | None = None) -> int:
    """archive_copies_of() for a JD file, skipping the file's own row."""
    try:
        with open(jd_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(meta, dict):
        return 0
    own_id = (
        meta.get("source_job_id")
        or meta.get("id")
        or jd_manager.compute_job_key(jd_path)
    )
    return archive_copies_of(meta, exclude_ids={own_id}, profile=profile)


def archive_copies_of_id(job_id: str, profile: str | None = None) -> int:
    """archive_copies_of() for a database-only job, skipping the job itself."""
    conn = db.get_db(profile)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT company, title, dedup_hash, metadata_json FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return 0
    meta = json.loads(row["metadata_json"] or "{}")
    meta.setdefault("company", row["company"])
    meta.setdefault("title", row["title"])
    meta.setdefault("dedup_hash", row["dedup_hash"])
    return archive_copies_of(meta, exclude_ids={job_id}, profile=profile)


def _own_row_keys(pending_file_paths: list[str]) -> tuple[set[str], set[str]]:
    """Ids and dedup_hashes of the data.db rows that MIRROR a pending file.

    A file-backed job may also have its OWN data.db row, which
    jd_manager._sync_jd_to_db() keys by the file's source_job_id, else its
    id, else compute_job_key(path). That row mirrors the file rather than
    duplicating it, so it is skipped by the caller (the file represents the
    job); any OTHER row for the same posting -- a copy under a different id
    -- still clusters with the file and is archived as a genuine duplicate.

    Matching that id alone is not enough: db.upsert_job() MERGES into an
    existing row with the same dedup_hash instead of inserting, so when a
    scan wrote the row before the file's sync ran, the file's own row
    survives under the SCANNER's id and none of the three keys above names
    it. Such a row then looked like a genuine duplicate of its own file
    (6 of one profile's roles on 2026-09-15). The row's dedup_hash is
    returned too.
    """
    own_row_ids: set[str] = set()
    own_row_hashes: set[str] = set()
    for path in pending_file_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                f_data = json.load(f)
        except Exception:
            continue
        if not isinstance(f_data, dict):
            continue
        own_row_ids.add(
            str(
                f_data.get("source_job_id")
                or f_data.get("id")
                or jd_manager.compute_job_key(path)
            )
        )
        own_hash = f_data.get("dedup_hash") or db.compute_job_dedup_hash(
            f_data.get("job_title") or f_data.get("title") or "",
            f_data.get("company_name") or f_data.get("company") or "",
            f_data.get("location") or "",
        )
        if own_hash:
            own_row_hashes.add(str(own_hash))
    return own_row_ids, own_row_hashes


def _db_row_items(
    db_rows: list, own_row_ids: set[str], own_row_hashes: set[str]
) -> dict:
    """Clusterable entries for every pending row that is not a file's mirror."""
    items = {}
    for r in db_rows:
        if str(r["id"]) in own_row_ids:
            continue
        if r["dedup_hash"] and str(r["dedup_hash"]) in own_row_hashes:
            continue
        meta = json.loads(r["metadata_json"] or "{}")
        eval_data = meta.get("_evaluation") or {}
        score = r["final_score"] or eval_data.get("composite_score") or 0.0
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
            "url": get_job_url(meta),
            "norm_tc": (c_norm, t_norm),
            "norm_tcl": (c_norm, t_norm, normalize_text(r["location"])),
            "meta": meta,
            "created_at": r["created_at"] or "",
        }
    return items


def _file_items(pending_file_paths: list[str]) -> dict:
    """Clusterable entries for every pending JD file on disk."""
    items = {}
    for p in pending_file_paths:
        try:
            with open(p, "r", encoding="utf-8") as f:
                f_data = json.load(f)
            c = f_data.get("company_name") or f_data.get("company") or ""
            t = f_data.get("job_title") or f_data.get("title") or ""
            eval_data = f_data.get("_evaluation") or {}
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
                "score": eval_data.get("composite_score") or 0.0,
                "url": get_job_url(f_data),
                "norm_tc": (c_norm, t_norm),
                "norm_tcl": (c_norm, t_norm, normalize_text(f_data.get("location"))),
                "meta": f_data,
                "created_at": "",
            }
        except Exception:
            pass
    return items


def _cluster_items(items: dict) -> dict:
    """Union-finds `items` into clusters, keyed by each cluster's root id.

    Three independent passes union a pair: an identical dedup_hash, an
    identical (URL, company, title), and an identical (company, title).
    """
    parent = {i: i for i in items}

    def find(i):
        if parent[i] != i:
            parent[i] = find(parent[i])
        return parent[i]

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    def union_all(groups: dict) -> None:
        for ids in groups.values():
            for o in ids[1:]:
                union(ids[0], o)

    # 1. Union by dedup_hash
    by_hash: dict[str, list[str]] = {}
    for i, it in items.items():
        h = it["dedup_hash"]
        if h:
            by_hash.setdefault(h, []).append(i)
    union_all(by_hash)

    # 2. Union by (source URL, normalized company). URL alone is not safe:
    # some ATS platforms (observed: ADP Workforce Now) route every posting
    # through the exact same generic recruitment-shell URL regardless of
    # employer or role, so keying on URL alone unioned four unrelated jobs
    # from four different companies into a single "duplicate" cluster.
    # Pairing with company matches job_key_known()'s existing convention
    # for the same reason (see its docstring).
    # ...and the same normalized title. URL + company still merged DIFFERENT
    # roles: live (2026-09-13), "Data Scientist, Level 2" was archived into
    # "Level 1" at the same employer and "Managing Consultant" into
    # "Consultant" -- sibling postings sharing a careers-search or listing
    # URL. Different titles are different openings until proven otherwise;
    # a missed reworded duplicate costs one evaluation, a lost role costs
    # an application.
    by_url: dict[tuple[str, str, str], list[str]] = {}
    for i, it in items.items():
        u = it["url"]
        c_norm, t_norm = it["norm_tc"]
        if u and len(u) > 15 and c_norm and t_norm:
            by_url.setdefault((u, c_norm, t_norm), []).append(i)
    union_all(by_url)

    # 3. Union by exact normalized company + title
    by_tc: dict[tuple[str, str], list[str]] = {}
    for i, it in items.items():
        c, t = it["norm_tc"]
        if c and t:
            by_tc.setdefault((c, t), []).append(i)
    union_all(by_tc)

    clusters: dict[str, list[str]] = {}
    for i in items:
        clusters.setdefault(find(i), []).append(i)
    return clusters


def _rank_cluster(items: dict, member_ids: list[str]) -> list[str]:
    """Orders a cluster best-first, so the head is the copy worth keeping.

    1. is_file (True first)
    2. score (highest first)
    3. richness of metadata (keys count)
    4. created_at (most recent first)
    """
    return sorted(
        member_ids,
        key=lambda cid: (
            1 if items[cid]["is_file"] else 0,
            items[cid]["score"],
            len(items[cid]["meta"]),
            items[cid]["created_at"],
        ),
        reverse=True,
    )


# Fields a loser can contribute to the winner: a copy often carries
# enrichment the winner never got, and losing it to the archive would
# mean paying for it again.
_MERGEABLE_FIELDS = (
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
)


def _merged_winner_meta(items: dict, winner_id: str, losers: list[str]) -> dict:
    """The winner's metadata, fill-only from each loser's."""
    winner_meta = dict(items[winner_id]["meta"])
    for loser_id in losers:
        loser_meta = items[loser_id]["meta"]
        for field in _MERGEABLE_FIELDS:
            if loser_meta.get(field) and not winner_meta.get(field):
                winner_meta[field] = loser_meta[field]
    return winner_meta


def _persist_winner(
    cursor, winner_item: dict, winner_id: str, winner_meta: dict
) -> int:
    """Writes merged metadata back. Returns 1 if anything was written."""
    if winner_meta == winner_item["meta"]:
        return 0
    if not winner_item["is_file"]:
        cursor.execute(
            "UPDATE jobs SET metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (json.dumps(winner_meta), winner_id),
        )
        return 1
    # Winner is a file -- update file on disk if missing fields merged
    try:
        with open(winner_id, "w", encoding="utf-8") as f:
            json.dump(winner_meta, f, indent=2, ensure_ascii=False)
        return 1
    except Exception as e:
        print(f"Warning: could not update winner file {winner_id}: {e}")
        return 0


def _archive_losers(cursor, items: dict, losers: list[str], winner_id: str) -> int:
    """Archives every loser in a cluster. Returns how many were archived."""
    archived = 0
    for loser_id in losers:
        loser_item = items[loser_id]
        loser_meta = dict(loser_item["meta"])
        loser_meta["archived_reason"] = "duplicate"
        loser_meta["canonical_job_id"] = winner_id

        if not loser_item["is_file"]:
            cursor.execute(
                "UPDATE jobs SET status = 'archived', metadata_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (json.dumps(loser_meta), loser_id),
            )
            archived += 1
        elif loser_item["file_path"] and os.path.exists(loser_item["file_path"]):
            try:
                jd_manager.archive_jd(loser_item["file_path"])
                archived += 1
            except Exception as e:
                print(f"Warning: could not archive file {loser_item['file_path']}: {e}")
    return archived


def run_deduplication(profile: str | None = None, dry_run: bool = True) -> dict:
    conn = db.get_db(profile)
    conn.row_factory = sqlite3.Row

    db_rows = conn.execute("SELECT * FROM jobs WHERE status = 'pending'").fetchall()
    pending_file_paths = jd_manager.get_pending_jds()
    own_row_ids, own_row_hashes = _own_row_keys(pending_file_paths)

    items = _db_row_items(db_rows, own_row_ids, own_row_hashes)
    items.update(_file_items(pending_file_paths))

    clusters = _cluster_items(items)
    multi_clusters = {k: v for k, v in clusters.items() if len(v) > 1}

    archived_count = 0
    updated_winners = 0
    sample_clusters = []

    cursor = conn.cursor()

    for member_ids in multi_clusters.values():
        sorted_members = _rank_cluster(items, member_ids)
        winner_id = sorted_members[0]
        losers = sorted_members[1:]
        winner_item = items[winner_id]

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

        winner_meta = _merged_winner_meta(items, winner_id, losers)
        updated_winners += _persist_winner(cursor, winner_item, winner_id, winner_meta)
        archived_count += _archive_losers(cursor, items, losers, winner_id)

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
