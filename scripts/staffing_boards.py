"""Staffing-agency job boards the user has been asked to watch.

A local recruiter saying "keep an eye on our board" is a real lead, but
agency boards are not ATS boards: they post for confidential clients, run
on small WordPress/job-board vendors, and are on no aggregator this project
scans. This module is the scan source ("staffing_boards" in
scan.SOURCE_FETCHERS) that reads them, configured per profile in
scan_filters.yml:

    staffing_boards:
      - name: Lighthouse Technology Services
        url: https://jobs.lhtservices.com/
        type: hmg
      - name: ComputerPeople
        url: https://jobs.cpstaffing.com/?_select_area=cp-buf
        type: jsonld

Two adapters cover every board seen so far, and a new board is a config
entry rather than code when it fits one of them:

* ``jsonld`` -- the listing page links to detail pages that embed a
  schema.org ``JobPosting`` (the WP Job Manager family, and most job-board
  plugins, because Google for Jobs requires it). FacetWP pagination
  (``_paged=N``, with ``total_pages`` in the page's own JSON) is followed.
  ``link_pattern`` (a regex) narrows which links count as postings; the
  default is any same-host link with "/job" in its path.
* ``hmg`` -- Haley Marketing Group's "hmg-jb" boards, whose postings come
  from a ticketed JSON endpoint that only answers the page's own scripts.
  ``scan-hmg-board.mjs`` loads the page once in headless Chromium and
  reads every posting from inside it.

Every posting carries ``staffing_agency`` (the board's name), which is what
the dashboard's category filter keys on. The client is usually unnamed, so
``company_name`` is the agency. Postings pass the same excluded-title and
location gates Indeed results do (scan_indeed._admit_indeed_job) -- an
agency board lists roles nationwide (41 ComputerPeople postings, 10 of them
in the Buffalo area) and the radius is what keeps that to the local ones.
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

import requests

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
HMG_SCRIPT = os.path.join(SCRIPTS_DIR, "scan-hmg-board.mjs")

SOURCE_PLATFORM = "staffing_board"
HTTP_TIMEOUT_SECONDS = 20
HMG_TIMEOUT_SECONDS = 150
MAX_LISTING_PAGES = 10
MAX_POSTINGS_PER_BOARD = 200
DETAIL_FETCH_GAP_SECONDS = 0.5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
_TEST_NETWORK_ENV = "RESUME_ALLOW_TEST_NETWORK"

_JSONLD_BLOCK = re.compile(
    r"<script[^>]*application/ld\+json[^>]*>(.*?)</script>", re.S | re.I
)
_HREF = re.compile(r"""href=["']([^"'#]+)["']""", re.I)
_TOTAL_PAGES = re.compile(r'"total_pages"\s*:\s*(\d+)')
# Agencies pin an always-open "join our talent network" post among the
# real ones; it is a resume drop, not a role.
_PLACEHOLDER_TITLE = re.compile(
    r"talent (network|community|pool)|general application|submit your resume",
    re.I,
)

_EMPLOYMENT_TYPES = {
    "FULL_TIME": "Full-time",
    "PART_TIME": "Part-time",
    "CONTRACTOR": "Contract",
    "TEMPORARY": "Temporary",
    "INTERN": "Internship",
    "PER_DIEM": "Per diem",
    "OTHER": "",
}


def _network_blocked() -> bool:
    """Same escape hatch as websearch_ddg: no live requests under unittest."""
    return "unittest" in sys.modules and not os.environ.get(_TEST_NETWORK_ENV)


def configured_boards() -> list[dict]:
    """The active profile's ``staffing_boards`` entries, validated.

    An entry with no url or an unknown type is skipped with a warning
    rather than failing the whole source. Returns [] when the block is
    absent -- the source is then a no-op, like indeed_watch_companies."""
    import scan_boards

    try:
        raw = scan_boards._load_filters().get("staffing_boards") or []
    except (OSError, AttributeError):
        return []
    boards = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("url"):
            logging.warning(f"staffing_boards: skipping entry without a url: {entry!r}")
            continue
        board_type = (entry.get("type") or "jsonld").lower()
        if board_type not in ADAPTERS:
            logging.warning(
                f"staffing_boards: unknown type {board_type!r} for {entry['url']} "
                f"(known: {', '.join(ADAPTERS)})"
            )
            continue
        boards.append(
            {
                "name": entry.get("name") or urlparse(entry["url"]).hostname or "",
                "url": entry["url"],
                "type": board_type,
                "link_pattern": entry.get("link_pattern"),
            }
        )
    return boards


# -- jsonld adapter -------------------------------------------------------


def _get(session: requests.Session, url: str) -> str:
    resp = session.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.text


def _with_query(url: str, **params) -> str:
    parts = urlparse(url)
    query = parse_qs(parts.query)
    for key, value in params.items():
        query[key] = [str(value)]
    return urlunparse(parts._replace(query=urlencode(query, doseq=True)))


def _posting_links(html: str, base_url: str, link_pattern: str | None) -> list[str]:
    """Same-host links that look like individual postings, in page order."""
    host = urlparse(base_url).hostname
    pattern = re.compile(link_pattern) if link_pattern else None
    seen, links = set(), []
    for href in _HREF.findall(html):
        url = urljoin(base_url, href)
        parts = urlparse(url)
        if parts.hostname != host:
            continue
        if pattern is not None:
            if not pattern.search(url):
                continue
        elif "/job" not in parts.path.lower() or parts.path.rstrip("/").endswith(
            ("/jobs", "/job")
        ):
            continue
        url = urlunparse(parts._replace(query="", fragment=""))
        if url not in seen:
            seen.add(url)
            links.append(url)
    return links


def _job_posting_from_html(html: str) -> dict | None:
    """The first schema.org JobPosting in a page's JSON-LD, or None."""
    for block in _JSONLD_BLOCK.findall(html):
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for item in items:
            if not isinstance(item, dict):
                continue
            kind = item.get("@type")
            if kind == "JobPosting" or (
                isinstance(kind, list) and "JobPosting" in kind
            ):
                return item
    return None


def _jsonld_location(posting: dict) -> str:
    places = posting.get("jobLocation") or []
    if isinstance(places, dict):
        places = [places]
    for place in places:
        address = (place or {}).get("address") or {}
        if isinstance(address, str):
            return address
        city = address.get("addressLocality") or ""
        region = address.get("addressRegion") or ""
        if city or region:
            return ", ".join(p for p in (city, region) if p)
    return ""


def _jsonld_salary(posting: dict) -> str:
    salary = posting.get("baseSalary") or {}
    if not isinstance(salary, dict):
        return ""
    value = salary.get("value") or {}
    if not isinstance(value, dict):
        return f"${value}" if value else ""
    low, high = value.get("minValue"), value.get("maxValue")
    unit = (value.get("unitText") or "").lower()
    if not (low or high or value.get("value")):
        return ""

    def money(amount) -> str:
        try:
            return f"${float(amount):,.0f}"
        except (TypeError, ValueError):
            return str(amount)

    span = (
        f"{money(low)} - {money(high)}"
        if low and high
        else money(low or high or value.get("value"))
    )
    return f"{span} per {unit}" if unit else span


def _job_from_jsonld(posting: dict, url: str, board: dict) -> dict:
    import scan_boards

    raw_type = posting.get("employmentType") or ""
    if isinstance(raw_type, list):
        raw_type = raw_type[0] if raw_type else ""
    identifier = posting.get("identifier") or {}
    location = _jsonld_location(posting)
    remote = posting.get("jobLocationType") == "TELECOMMUTE"
    salary = _jsonld_salary(posting)
    description = scan_boards._html_to_text(posting.get("description") or "")
    if salary and salary not in description:
        description = f"Salary: {salary}\n\n{description}"
    return {
        "job_title": scan_boards._html_to_text(posting.get("title") or ""),
        "company_name": board["name"],
        "source_platform": SOURCE_PLATFORM,
        "source_job_id": (
            str(identifier.get("value"))
            if isinstance(identifier, dict) and identifier.get("value")
            else None
        ),
        "source_url": url,
        "location": location or ("Remote" if remote else ""),
        "is_remote": remote or None,
        "posted_at": posting.get("datePosted") or "",
        "employment_type": _EMPLOYMENT_TYPES.get(str(raw_type).upper(), raw_type),
        "salary": salary,
        "description": description,
        "staffing_agency": board["name"],
    }


def _fetch_jsonld_board(board: dict, activity=None) -> list[dict]:
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    first = _get(session, board["url"])
    pages = [first]
    total = _TOTAL_PAGES.search(first)
    for page in range(
        2, min(int(total.group(1)) if total else 1, MAX_LISTING_PAGES) + 1
    ):
        pages.append(_get(session, _with_query(board["url"], _paged=page)))

    links: list[str] = []
    for html in pages:
        for link in _posting_links(html, board["url"], board.get("link_pattern")):
            if link not in links:
                links.append(link)
    links = links[:MAX_POSTINGS_PER_BOARD]

    jobs = []
    for i, link in enumerate(links):
        if i:
            time.sleep(DETAIL_FETCH_GAP_SECONDS)
        try:
            posting = _job_posting_from_html(_get(session, link))
        except requests.RequestException as exc:
            logging.warning(f"staffing_boards: {link} failed: {exc}")
            continue
        if posting is None:
            logging.info(f"staffing_boards: no JobPosting data on {link}")
            continue
        jobs.append(_job_from_jsonld(posting, link, board))
    return jobs


# -- hmg adapter ------------------------------------------------------------


def _hmg_posting_url(board_url: str, post: dict) -> str:
    """The board's own page for a posting. hmg-jb boards serve each posting
    at /jobs/<POST_ID>/<SEO_PERMALINK>; the post's own POST_SEO_URL wins
    when it carries one."""
    if str(post.get("POST_SEO_URL") or "").startswith("http"):
        return str(post["POST_SEO_URL"])
    parts = urlparse(board_url)
    path = f"/jobs/{post.get('POST_ID')}"
    if post.get("SEO_PERMALINK"):
        path += f"/{post['SEO_PERMALINK']}"
    return urlunparse((parts.scheme, parts.netloc, path, "", "", ""))


def _job_from_hmg(post: dict, board: dict) -> dict:
    import scan_boards

    title = (post.get("POST_TITLE") or post.get("POST_FIELD4") or "").strip()
    location = (post.get("POST_LOCATION") or "").strip()
    if not location:
        location = ", ".join(
            p for p in (post.get("POST_CITY"), post.get("POST_STATE")) if p
        )
    remote = str(post.get("POST_REMOTE_ALLOW") or "").lower() in {
        "1",
        "y",
        "yes",
        "true",
    }
    salary = (post.get("POST_SALARY") or "").strip()
    description = scan_boards._html_to_text(post.get("POST_DESCRIPTION") or "")
    if salary and salary not in description:
        description = f"Salary: {salary}\n\n{description}"
    return {
        "job_title": title,
        "company_name": board["name"],
        "source_platform": SOURCE_PLATFORM,
        "source_job_id": str(post.get("POST_ID") or "") or None,
        "source_url": _hmg_posting_url(board["url"], post),
        "location": location or ("Remote" if remote else ""),
        "is_remote": remote or None,
        "posted_at": post.get("POST_CREATE_DATE") or "",
        "employment_type": (post.get("POST_EMPLOYMENT_TYPE") or "").strip(),
        "salary": salary,
        "description": description,
        "staffing_agency": board["name"],
    }


def _fetch_hmg_board(board: dict, activity=None) -> list[dict]:
    try:
        proc = subprocess.run(
            ["node", HMG_SCRIPT, board["url"]],
            cwd=SCRIPTS_DIR,
            capture_output=True,
            text=True,
            timeout=HMG_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        logging.warning(f"staffing_boards: {board['url']} render failed: {exc}")
        return []
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        logging.warning(f"staffing_boards: {board['url']} returned unreadable output")
        return []
    if payload.get("error"):
        logging.warning(f"staffing_boards: {board['url']}: {payload['error']}")
        return []
    posts = payload.get("posts") or []
    return [_job_from_hmg(p, board) for p in posts[:MAX_POSTINGS_PER_BOARD]]


ADAPTERS = {"jsonld": _fetch_jsonld_board, "hmg": _fetch_hmg_board}


def fetch_staffing_board_jobs(activity=None) -> list:
    """Every configured board's postings that clear the title and location
    gates. Never raises: a board that fails is logged and skipped, so one
    agency redesigning its site cannot sink the rest of a scan."""
    import scan_indeed

    boards = configured_boards()
    if not boards or _network_blocked():
        return []
    if activity is not None:
        activity.start_source(len(boards), label="Fetching")

    jobs = []
    for board in boards:
        if activity is not None:
            activity.step("discovery", board["name"], f"Checking {board['name']}")
        try:
            found = ADAPTERS[board["type"]](board, activity=activity)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning(f"staffing_boards: {board['url']} failed: {exc}")
            continue
        kept = [
            job
            for job in found
            if job["job_title"]
            and not _PLACEHOLDER_TITLE.search(job["job_title"])
            and scan_indeed._admit_indeed_job(job)
        ]
        logging.info(
            f"staffing_boards: {board['name']}: kept {len(kept)} of {len(found)} posting(s)."
        )
        jobs.extend(kept)
    return jobs
