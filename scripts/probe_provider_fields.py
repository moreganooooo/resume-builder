"""Measure which structured fields each job provider actually publishes.

Answers one question per provider: does it give us **employment type**
and **compensation** as structured data, and on what fraction of its
postings? That determines whether a role-attribute filter can gate at
scan time (Stage 1) or has to wait for the LLM evaluation (Stage 2) --
see docs/superpowers/specs/2026-08-29-role-attribute-filters-design.md.

This exists because the spec's provider table was WRONG about greenhouse
-- the largest ATS source in the corpus -- for two revisions, purely
because it was reasoned about rather than measured. A provider whose
field we assume and never verify defeats a filter *quietly*: the field
comes back absent, the posting lands in the permissive "unknown" bucket,
and the filter reports success while examining nothing. The adzuna
"Buffalo, Erie County" bug was exactly this shape.

Read-only. Hits public endpoints only, never writes, and is not part of
any pipeline -- run it deliberately:

    python scripts/probe_provider_fields.py              # everything
    python scripts/probe_provider_fields.py --only ashby lever
    python scripts/probe_provider_fields.py --json out.json

WORKDAY: the listing endpoint returns five fields and no employment
type, which is why it was written off as unmeasurable. The per-posting
DETAIL endpoint carries `timeType` at 100% ("Full time" / "Part time"),
and scan_boards already fetches that page for its description text --
so the field is free. Measured 25% part-time on one tracked tenant,
which is exactly the population a part-time filter exists to separate.

DEAD vs. QUIET: four providers reported zero postings. Two are dead
upstream (see DEAD_PROVIDERS) and two were probe bugs -- powertofly is
JSON served from a /rss path behind a 308, and was parsed as XML. A
zero is never self-explanatory; it has to be chased to a cause.

PER-BOARD VARIANCE -- the central methodological finding. Measured over
24 boards per provider (575 greenhouse / 390 ashby / 79 lever postings):

    employment type   greenhouse 0/0/0%    lever 94/100/100%   ashby 100/100/100%
    salary            greenhouse 0/80/100% lever 0/0/100%      ashby 0/68/100%
                                 (min/median/max across boards)

Employment type is a PROVIDER property: near-zero variance, so a
provider-level number is meaningful and Stage 1 can gate on it.
Salary is an EMPLOYER property: every provider spans the full 0-100%
range, so NO provider-level salary coverage number means anything. Any
such figure is sampling noise dressed as a fact -- which is exactly what
earlier revisions of the spec recorded. Report salary coverage from what
a scan actually observed, never from a per-provider expectation.

ATS providers are sampled using REAL slugs from the active profile's
tracked_companies.yml, not invented ones: a guessed slug 404s (or, on
SmartRecruiters, returns 200 with an empty list) and reads as "provider
has no fields" when the truth is "company does not exist."
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable

TIMEOUT = 25
UA = "Mozilla/5.0 (compatible; resume-builder provider probe)"

# Sample size per provider. Small on purpose: this is a coverage
# estimate, not a census, and these are other people's servers.
SAMPLE_BOARDS = 4
MAX_POSTINGS = 150


def _request(url: str, headers: dict | None = None) -> urllib.request.Request:
    """Build a request, refusing any scheme but https.

    Board slugs come from a profile's own tracked_companies.yml and are
    interpolated into these URLs, so an https-only check is what keeps a
    hand-edited entry from turning a probe into a file:// read.
    """
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-https probe URL: {url!r}")
    return urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})


def _get(url: str, headers: dict | None = None) -> Any:
    req = _request(url, {"Accept": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:  # nosec B310
        return json.load(resp)


def _post(url: str, payload: dict) -> Any:
    req = _request(
        url, {"Content-Type": "application/json", "Accept": "application/json"}
    )
    data = json.dumps(payload).encode()
    with urllib.request.urlopen(req, data=data, timeout=TIMEOUT) as resp:  # nosec B310
        return json.load(resp)


def _get_text(url: str) -> str:
    with urllib.request.urlopen(_request(url), timeout=TIMEOUT) as resp:  # nosec B310
        return resp.read().decode("utf-8", "replace")


# Salary in free text. Deliberately conservative -- a bare "$50" is more
# often a product price than a wage, so require a thousands separator, a
# K suffix, or an explicit per-hour unit.
SALARY_RE = re.compile(
    r"\$\s?\d{2,3},\d{3}"
    r"|\$\s?\d{2,3}(?:\.\d+)?\s?[kK]\b"
    r"|\$\s?\d{1,3}(?:\.\d{2})?\s?(?:/|per\s)\s?(?:hr|hour)",
    re.IGNORECASE,
)


class Result:
    """One provider's measured field coverage."""

    def __init__(self, name: str, kind: str):
        self.name = name
        self.kind = kind  # ats | api | rss | keyed | special
        self.n = 0
        self.employment = 0
        self.salary = 0
        self.employment_field = ""
        self.salary_field = ""
        self.values: dict[str, int] = {}
        self.error = ""
        self.notes: list[str] = []

    def observe_employment(self, value: Any, field: str = "") -> None:
        if value in (None, "", [], {}):
            return
        self.employment += 1
        self.employment_field = field or self.employment_field
        key = str(value)[:40]
        self.values[key] = self.values.get(key, 0) + 1

    def observe_salary(self, present: bool, field: str = "") -> None:
        if present:
            self.salary += 1
            self.salary_field = field or self.salary_field

    def pct(self, count: int) -> str:
        return f"{count / self.n:.0%}" if self.n else "-"

    def row(self) -> str:
        if self.error:
            return f"{self.name:<22} {self.kind:<8} ERROR: {self.error[:44]}"
        return (
            f"{self.name:<22} {self.kind:<8} n={self.n:<5} "
            f"employment={self.pct(self.employment):<5} ({self.employment_field or '-'})"
            f"  salary={self.pct(self.salary):<5} ({self.salary_field or '-'})"
        )

    def to_dict(self) -> dict:
        return {
            "provider": self.name,
            "kind": self.kind,
            "n": self.n,
            "employment_pct": round(self.employment / self.n, 3) if self.n else None,
            "employment_field": self.employment_field,
            "salary_pct": round(self.salary / self.n, 3) if self.n else None,
            "salary_field": self.salary_field,
            "employment_values": dict(
                sorted(self.values.items(), key=lambda kv: -kv[1])[:8]
            ),
            "error": self.error,
            "notes": self.notes,
        }


# --------------------------------------------------------------------
# ATS providers -- slug-driven, sampled from tracked_companies.yml
# --------------------------------------------------------------------


def load_slugs(profile: str | None = None) -> dict[str, list[str]]:
    """Real board slugs per provider, parsed from tracked_companies.yml.

    Guessed slugs are worse than no data: SmartRecruiters answers 200
    with totalFound: 0 for a slug that does not exist, which reads
    identically to a provider that publishes nothing.
    """
    import yaml

    sys.path.insert(0, "scripts")
    import profile_paths

    root = (
        profile_paths.profile_root(profile) if profile else profile_paths.profile_root()
    )
    path = f"{root}/board_scanner/tracked_companies.yml"
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    entries = raw.get("tracked_companies", raw) if isinstance(raw, dict) else raw

    patterns = {
        "greenhouse": r"greenhouse\.io/(?:v1/boards/)?([\w-]+)",
        "lever": r"lever\.co/([\w-]+)",
        "ashby": r"ashbyhq\.com/(?:posting-api/job-board/)?([\w-]+)",
        "smartrecruiters": r"smartrecruiters\.com/(?:v1/companies/)?([\w-]+)",
        "recruitee": r"([\w-]+)\.recruitee\.com",
        "workable": r"workable\.com/([\w-]+)",
        "workday": r"([\w-]+)\.(?:wd\d+\.)?myworkdayjobs\.com",
    }
    found: dict[str, list[str]] = {k: [] for k in patterns}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            continue
        blob = f"{entry.get('api') or ''} {entry.get('careers_url') or ''}"
        for provider, pattern in patterns.items():
            match = re.search(pattern, blob)
            if match and match.group(1) not in found[provider]:
                found[provider].append(match.group(1))
    return found


def probe_greenhouse(slugs: list[str]) -> Result:
    r = Result("greenhouse", "ats")
    for slug in slugs:
        try:
            jobs = _get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
            )["jobs"]
        except Exception:
            continue
        for j in jobs[:MAX_POSTINGS]:
            r.n += 1
            # boards-api exposes no employment field at all; metadata is
            # employer-defined free text and is NOT a reliable source.
            r.observe_employment(None)
            if j.get("pay_input_ranges"):
                r.observe_salary(True, "pay_input_ranges")
            else:
                r.observe_salary(
                    bool(SALARY_RE.search(j.get("content") or "")), "content prose"
                )
    r.notes.append("no structured employment field; salary only in prose")
    return r


def probe_lever(slugs: list[str]) -> Result:
    r = Result("lever", "ats")
    for slug in slugs:
        try:
            jobs = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        except Exception:
            continue
        for j in jobs[:MAX_POSTINGS]:
            r.n += 1
            r.observe_employment(
                (j.get("categories") or {}).get("commitment"), "categories.commitment"
            )
            r.observe_salary(bool(j.get("salaryRange")), "salaryRange")
    return r


def probe_ashby(slugs: list[str]) -> Result:
    r = Result("ashby", "ats")
    hidden = 0
    for slug in slugs:
        try:
            jobs = _get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
                "?includeCompensation=true"
            ).get("jobs", [])
        except Exception:
            continue
        for j in jobs[:MAX_POSTINGS]:
            r.n += 1
            r.observe_employment(j.get("employmentType"), "employmentType")
            comp = j.get("compensation") or {}
            r.observe_salary(
                bool(comp.get("scrapeableCompensationSalarySummary")),
                "compensation",
            )
            if comp and not j.get("shouldDisplayCompensationOnJobPostings"):
                hidden += 1
    if hidden:
        r.notes.append(f"{hidden} postings carry comp but opt out of displaying it")
    return r


def probe_smartrecruiters(slugs: list[str]) -> Result:
    r = Result("smartrecruiters", "ats")
    for slug in slugs:
        try:
            payload = _get(
                f"https://api.smartrecruiters.com/v1/companies/{slug}"
                "/postings?limit=100"
            )
        except Exception:
            continue
        for j in payload.get("content", [])[:MAX_POSTINGS]:
            r.n += 1
            toe = j.get("typeOfEmployment") or {}
            r.observe_employment(toe.get("label"), "typeOfEmployment.label")
            r.observe_salary(bool(j.get("compensation")), "compensation")
    return r


def probe_recruitee(slugs: list[str]) -> Result:
    r = Result("recruitee", "ats")
    for slug in slugs:
        try:
            offers = _get(f"https://{slug}.recruitee.com/api/offers/")["offers"]
        except Exception:
            continue
        for j in offers[:MAX_POSTINGS]:
            r.n += 1
            r.observe_employment(
                j.get("employment_type_code") or j.get("employment_type"),
                "employment_type_code",
            )
            r.observe_salary(bool(j.get("salary") or j.get("min_hours")), "salary")
    return r


def probe_workable(slugs: list[str]) -> Result:
    r = Result("workable", "ats")
    for slug in slugs:
        try:
            md = _get_text(f"https://apply.workable.com/{slug}/jobs.md")
        except Exception:
            continue
        # Columns: Title | Department | Location | Type | Salary |
        # Posted | Details. Parsed from the RIGHT, because a title
        # containing a pipe ("AI Solutions Consultant | 1099
        # Consultant") shifts every left-indexed column -- observed
        # live on panorama-education. workable.mjs indexes from the
        # left and has the same latent bug.
        for line in md.splitlines():
            if not line.startswith("|") or "---" in line:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 7 or cells[0].lower() == "title":
                continue
            kind, salary = cells[-4], cells[-3]
            r.n += 1
            blank = {"", "-", "\u2014", "\u2013"}
            r.observe_employment(None if kind in blank else kind, "md table 'Type'")
            r.observe_salary(salary not in blank, "md table 'Salary'")
    return r


# --------------------------------------------------------------------
# Public JSON APIs -- no slug needed
# --------------------------------------------------------------------


def _simple_api(
    name: str,
    url: str,
    extract: Callable[[Any], list],
    employment_key: Callable[[dict], Any],
    salary_key: Callable[[dict], Any],
    employment_field: str,
    salary_field: str,
    kind: str = "api",
) -> Result:
    r = Result(name, kind)
    try:
        payload = _get(url)
        items = [x for x in extract(payload) if isinstance(x, dict)]
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        r.error = f"{type(exc).__name__}: {exc}"
        return r
    for j in items[:MAX_POSTINGS]:
        r.n += 1
        r.observe_employment(employment_key(j), employment_field)
        r.observe_salary(bool(salary_key(j)), salary_field)
    return r


def probe_public_apis() -> list[Result]:
    out = []
    out.append(
        _simple_api(
            "himalayas",
            "https://himalayas.app/jobs/api?limit=100",
            lambda p: p.get("jobs", []),
            lambda j: j.get("employmentType"),
            lambda j: j.get("minSalary") or j.get("maxSalary"),
            "employmentType",
            "minSalary/maxSalary",
        )
    )
    out.append(
        _simple_api(
            "remotive",
            "https://remotive.com/api/remote-jobs?limit=100",
            lambda p: p.get("jobs", []),
            lambda j: j.get("job_type"),
            lambda j: (j.get("salary") or "").strip(),
            "job_type",
            "salary (free text)",
        )
    )
    out.append(
        _simple_api(
            "jobicy",
            "https://jobicy.com/api/v2/remote-jobs?count=100",
            lambda p: p.get("jobs", []),
            lambda j: j.get("jobType"),
            lambda j: j.get("annualSalaryMin") or j.get("salaryMin"),
            "jobType",
            "annualSalaryMin",
        )
    )
    out.append(
        _simple_api(
            "workingnomads",
            "https://www.workingnomads.co/api/exposed_jobs/",
            lambda p: p if isinstance(p, list) else p.get("jobs", []),
            lambda j: j.get("job_type") or j.get("contract_type"),
            lambda j: j.get("salary"),
            "job_type",
            "salary",
        )
    )
    out.append(
        _simple_api(
            "themuse",
            "https://www.themuse.com/api/public/jobs?page=1",
            lambda p: p.get("results", []),
            # NOT employment type: themuse's `type` is the posting kind
            # ("external"), which is why an unvalidated probe reported
            # 100% coverage of a field that answers a different question.
            lambda j: None,
            lambda j: False,
            "none (type= posting kind)",
            "none",
        )
    )
    out.append(
        _simple_api(
            "fourdayweek",
            "https://4dayweek.io/api/jobs",
            lambda p: p if isinstance(p, list) else p.get("jobs", []),
            lambda j: j.get("job_type") or j.get("employment_type"),
            lambda j: j.get("salary_min") or j.get("min_salary") or j.get("salary"),
            "job_type",
            "salary_min",
        )
    )
    out.append(
        _simple_api(
            "remoteok",
            "https://remoteok.com/api",
            lambda p: [x for x in p if isinstance(x, dict) and x.get("position")],
            lambda j: j.get("job_type") or j.get("tags") and None,
            lambda j: j.get("salary_min"),
            "job_type",
            "salary_min",
        )
    )
    out.append(
        _simple_api(
            "powertofly",
            # Trailing slash matters: the bare path 308-redirects, and this
            # is a JSON endpoint despite the /rss name. It was probed as RSS
            # for its whole existence, found no <item> elements, and reported
            # zero postings -- indistinguishable from a dead feed.
            "https://powertofly.com/jobs/rss/",
            lambda p: p.get("items", []),
            # "type" here is workplace mode ("Onsite"/"Remote"), NOT an
            # employment type. Same trap as themuse's "type".
            lambda j: None,
            lambda j: None,
            "none (type= is workplace mode)",
            "none",
        )
    )
    return out


# Providers whose upstream no longer exists. Kept as an explicit registry
# rather than deleted, because a scanner that silently contributes zero
# postings is indistinguishable from one that is merely having a quiet
# week -- naming the corpse is the whole point.
DEAD_PROVIDERS = {
    "crunchboard": (
        "https://www.crunchboard.com/jobs.rss 301-redirects to the "
        "jobboard.io marketing homepage (HTML, no feed). CrunchBoard is "
        "gone; the provider can never return a posting."
    ),
    "ycombinator": (
        "Algolia app id 45bwydsgqq no longer has DNS records "
        "(45bwydsgqq-dsn.algolia.net does not resolve, while "
        "latency-dsn.algolia.net does -- so this is a decommissioned app, "
        "not a network problem). Every scan fails at DNS and yields zero."
    ),
}


def _workday_tenants(boards: int, seed: int) -> list[tuple[str, str, str]]:
    """(base_url, tenant, board) triples from real careers_url values.

    Workday needs three parts, not a slug: the host carries the tenant
    AND its datacenter (wd1/wd5/...), and the board name is a path
    segment. Nothing about them is guessable.
    """
    import yaml

    sys.path.insert(0, "scripts")
    import profile_paths

    path = f"{profile_paths.profile_root()}/board_scanner/tracked_companies.yml"
    with open(path) as fh:
        raw = yaml.safe_load(fh)
    entries = raw.get("tracked_companies", raw) if isinstance(raw, dict) else raw
    out: list[tuple[str, str, str]] = []
    pattern = r"https://([\w-]+)\.(wd\d+\.)?myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)"
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("enabled") is False:
            continue
        blob = f"{entry.get('api') or ''} {entry.get('careers_url') or ''}"
        m = re.search(pattern, blob)
        if m:
            base = f"https://{m.group(1)}.{m.group(2) or ''}myworkdayjobs.com"
            triple = (base, m.group(1), m.group(3))
            if triple not in out:
                out.append(triple)
    random.Random(seed).shuffle(out)
    return out[:boards]


def probe_workday(boards: int, seed: int) -> Result:
    """Workday: listing is barren, DETAIL carries timeType at 100%.

    The listing endpoint returns exactly five fields and no employment
    type, which is why workday was written off as unmeasurable. The
    per-posting detail endpoint carries `timeType` ("Full time" /
    "Part time"). scan_boards already fetches that detail page for its
    description text, so this field costs no extra request.
    """
    r = Result("workday", "ats")
    tenants = _workday_tenants(boards, seed)
    if not tenants:
        r.error = "no myworkdayjobs careers_url in tracked_companies.yml"
        return r
    for base, tenant, board in tenants:
        api = f"{base}/wday/cxs/{tenant}/{board}"
        try:
            listing = _post(
                f"{api}/jobs",
                {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""},
            )
        except Exception as exc:  # noqa: BLE001
            r.notes.append(f"{tenant}: {type(exc).__name__}")
            continue
        for jp in (listing.get("jobPostings") or [])[:12]:
            path = str(jp.get("externalPath") or "")
            if "/job" not in path:
                continue
            try:
                info = _get(api + "/job" + path.split("/job", 1)[1])
            except Exception:  # noqa: BLE001
                continue
            info = info.get("jobPostingInfo") or {}
            r.n += 1
            r.observe_employment(info.get("timeType"), "jobPostingInfo.timeType")
            r.observe_salary(bool(info.get("payRange")), "jobPostingInfo.payRange")
            time.sleep(0.3)  # politeness; workday is a per-tenant server
    return r


def probe_rss() -> list[Result]:
    """RSS-backed boards. Structure caps what they can carry."""
    feeds = {
        "weworkremotely": "https://weworkremotely.com/remote-jobs.rss",
        "nodesk": "https://nodesk.co/remote-jobs/index.xml",
        "jobspresso": "https://jobspresso.co/jobs/feed/",
        "authenticjobs": "https://authenticjobs.com/?feed=job_feed",
        "realworkfromanywhere": "https://www.realworkfromanywhere.com/rss.xml",
    }
    out = []
    for name, url in feeds.items():
        r = Result(name, "rss")
        try:
            xml = _get_text(url)
        except Exception as exc:  # noqa: BLE001
            r.error = f"{type(exc).__name__}: {exc}"
            out.append(r)
            continue
        items = re.findall(r"<item>(.*?)</item>", xml, re.S | re.I)
        if not items:
            items = re.findall(r"<entry>(.*?)</entry>", xml, re.S | re.I)
        for item in items[:MAX_POSTINGS]:
            r.n += 1
            # RSS carries no standard employment/salary element; the only
            # honest measure is whether the text mentions either.
            m = re.search(
                r"\b(full[- ]?time|part[- ]?time|contract|freelance|intern)\b",
                item,
                re.I,
            )
            r.observe_employment(m.group(1) if m else None, "prose only")
            r.observe_salary(bool(SALARY_RE.search(item)), "prose only")
        r.notes.append("RSS: no structured fields possible; prose mentions only")
        out.append(r)
    return out


ATS_PROBES = {
    "greenhouse": probe_greenhouse,
    "lever": probe_lever,
    "ashby": probe_ashby,
    "smartrecruiters": probe_smartrecruiters,
    "recruitee": probe_recruitee,
    "workable": probe_workable,
}

# Providers this script cannot measure, and why. Listed explicitly so
# "unmeasured" never silently reads as "measured and empty".
UNMEASURED = {
    "adzuna": "needs ADZUNA_APP_ID/KEY; known teaser source (exactly 500 chars)",
    "jooble": "needs JOOBLE_API_KEY; known teaser source (~275 chars)",
    "usajobs": "needs USAJOBS_API_KEY + registered email header",
    "websearch": "search sweep, not a job API; no posting fields",
    "levelsfyi": "unofficial endpoint, blocks non-browser clients",
    "otta": "requires authenticated session",
    "wellfound": "requires authenticated session",
    "hackernews": "HN 'who is hiring' free-text comments; no fields by construction",
    "remote_curated": "a curated README of links, not postings",
    "linkedin": "python source (scan_linkedin.py); has work_model in metadata",
    "indeed": "python source via JobSpy; exposes job_type/min_amount/interval",
    "jobright": "python source; employment_type measured at 100% in corpus",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", help="probe just these providers")
    parser.add_argument("--json", help="write full results to this path")
    parser.add_argument("--profile", help="profile whose tracked_companies.yml to use")
    parser.add_argument("--boards", type=int, default=SAMPLE_BOARDS)
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="RNG seed for board sampling. Fixed by default: with a "
        "random seed, greenhouse salary coverage swung 37%% -> 70%% "
        "between consecutive runs purely from which boards were drawn, "
        "which reads as a provider changing rather than as sampling "
        "noise. See PER-BOARD VARIANCE in the module docstring.",
    )
    args = parser.parse_args()

    wanted = set(args.only or [])
    results: list[Result] = []

    random.seed(args.seed)
    slugs = load_slugs(args.profile)
    for name, probe in ATS_PROBES.items():
        if wanted and name not in wanted:
            continue
        picks = slugs.get(name, [])
        random.shuffle(picks)
        picks = picks[: args.boards]
        if not picks:
            r = Result(name, "ats")
            r.error = "no slugs in tracked_companies.yml"
            results.append(r)
            continue
        print(f"probing {name} ({', '.join(picks)}) ...", file=sys.stderr)
        try:
            results.append(probe(picks))
        except Exception as exc:  # noqa: BLE001
            r = Result(name, "ats")
            r.error = f"{type(exc).__name__}: {exc}"
            results.append(r)

    if not wanted or "workday" in wanted:
        print("probing workday tenants ...", file=sys.stderr)
        try:
            results.append(probe_workday(args.boards, args.seed))
        except Exception as exc:  # noqa: BLE001
            r = Result("workday", "ats")
            r.error = f"{type(exc).__name__}: {exc}"
            results.append(r)

    if not wanted or wanted & {"api", "public"}:
        print("probing public APIs ...", file=sys.stderr)
        results.extend(probe_public_apis())
        print("probing RSS feeds ...", file=sys.stderr)
        results.extend(probe_rss())

    print(f"\n{'PROVIDER':<22} {'KIND':<8} COVERAGE")
    print("-" * 96)
    for r in sorted(results, key=lambda r: (r.kind, r.name)):
        print(r.row())
        for note in r.notes:
            print(f"{'':<31}note: {note}")
        if r.values:
            top = ", ".join(
                f"{k}={v}"
                for k, v in sorted(r.values.items(), key=lambda kv: -kv[1])[:5]
            )
            print(f"{'':<31}values: {top}")

    print("\nDEAD UPSTREAM (verified, not a transient failure):")
    for name, why in sorted(DEAD_PROVIDERS.items()):
        print(f"  {name:<20} {why}")

    print("\nNOT MEASURED BY THIS SCRIPT (absence of data, not absence of fields):")
    for name, why in sorted(UNMEASURED.items()):
        print(f"  {name:<20} {why}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(
                {
                    "results": [r.to_dict() for r in results],
                    "unmeasured": UNMEASURED,
                },
                fh,
                indent=2,
            )
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
