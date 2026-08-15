"""
scan_jobright.py — JobRight API scanner, ported from job_automater's
scrapers/jobright_scraper.py.

Differences from the original: no MongoDB (store_job_data), no JSON backup
file, no progress_callback bridge -- this just returns a list of job dicts
in the same shape jd_manager.py already expects from a JD file
(source_job_id/job_title/company_name/etc.), for scan.py to dedupe and
write straight into jds/.
"""

import logging
import os
import time

import requests

import cli_art

JOBRIGHT_API_BASE_URL = "https://jobright.ai/swan/recommend/list/jobs"
JOBRIGHT_HEADERS = {
    "accept": "application/json, text/plain, */*", "accept-language": "en-US,en;q=0.9",
    "priority": "u=1, i", "referer": "https://jobright.ai/jobs/recommend",
    "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
    "sec-ch-ua-mobile": "?0", "sec-ch-ua-platform": '"macOS"', "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors", "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "x-client-type": "web",
}
JOBRIGHT_MAX_POSITION = 100
JOBRIGHT_POSITION_INCREMENT = 10
JOBRIGHT_REQUEST_DELAY_SECONDS = 2.0
MIN_MATCH_SCORE = 70  # jobs scoring below this are discarded, same as job_automater


def fetch_jobright_jobs(max_position: int = None, activity=None) -> list:
    """Fetches jobs from the JobRight API with pagination, filters out
    anything scoring below MIN_MATCH_SCORE, and returns a list of job dicts
    (same shape as job_automater's, which is already what jd_manager.py
    expects from a JD file)."""
    cookie_string = os.environ.get("JOBRIGHT_COOKIE_STRING")
    if not cookie_string:
        cli_art.cli_error("JOBRIGHT_COOKIE_STRING not configured. Skipping JobRight scan.")
        return []

    headers = JOBRIGHT_HEADERS.copy()
    headers["cookie"] = cookie_string

    end_position = max_position if max_position is not None else JOBRIGHT_MAX_POSITION
    jobs = []

    for position in range(0, end_position + 1, JOBRIGHT_POSITION_INCREMENT):
        page_url = f"{JOBRIGHT_API_BASE_URL}?refresh=false&sortCondition=0&position={position}"
        # Up to 11 paginated requests with a 2s backoff on a 500 -- without
        # a visible line per page, `resume scan --source jobright` looks
        # hung for 20+ seconds with logging.info's output invisible by
        # default.
        if activity is not None:
            activity.step("discovery", "JobRight", f"Fetching page (position {position}/{end_position})")
        else:
            cli_art.cli_info(f"Fetching JobRight jobs (position {position}/{end_position})...")
        logging.info(f"Fetching JobRight data for position {position}...")

        try:
            response = requests.get(page_url, headers=headers, timeout=30)
            if response.status_code == 500:
                cli_art.cli_error(f"HTTP 500 fetching position {position}, skipping.")
                time.sleep(JOBRIGHT_REQUEST_DELAY_SECONDS)
                continue

            response.raise_for_status()
            data = response.json()

            job_list = (data.get("result") or {}).get("jobList")
            if not job_list:
                logging.info(f"No more jobs at position {position}. Stopping.")
                break

            for item in job_list:
                job_result = item.get("jobResult")
                if not job_result:
                    continue

                job_id = job_result.get("jobId")
                job_title = job_result.get("jobTitle")
                company_result = item.get("companyResult") or {}
                company_name = company_result.get("companyName")

                match_score = item.get("displayScore") or item.get("matchScore") or 0
                if match_score < MIN_MATCH_SCORE:
                    continue
                if not job_title or not company_name:
                    continue

                apply_link = job_result.get("applyLink") or job_result.get("originalUrl")
                description_parts = [job_result.get("jobSummary", "")]
                resp = job_result.get("coreResponsibilities")
                if isinstance(resp, list):
                    description_parts.extend(resp)
                elif isinstance(resp, str):
                    description_parts.append(resp)
                description = "\n\n".join(filter(None, description_parts))

                jobs.append({
                    "status": "new",
                    "source_platform": "jobright",
                    "source_job_id": job_id,
                    "source_url": job_result.get("originalUrl"),
                    "match_score": match_score,
                    "application_type": "external" if apply_link else "unknown",
                    "application_url": apply_link,
                    "job_title": job_title,
                    "company_name": company_name,
                    "company_linkedin_url": company_result.get("companyLinkedinURL"),
                    "company_website": company_result.get("companyURL"),
                    "location": job_result.get("jobLocation"),
                    "is_remote": job_result.get("isRemote"),
                    "work_model": job_result.get("workModel"),
                    "publish_time": job_result.get("publishTime"),
                    "publish_time_desc": job_result.get("publishTimeDesc"),
                    "employment_type": job_result.get("employmentType"),
                    "seniority_level": job_result.get("jobSeniority"),
                    "description": description,
                    "description_html": None,
                    "job_summary": job_result.get("jobSummary"),
                    "skills": job_result.get("jdCoreSkills"),
                    "qualifications": job_result.get("qualifications"),
                    "core_responsibilities": job_result.get("coreResponsibilities"),
                    "social_connections": job_result.get("socialConnections"),
                    "personal_social_connections": job_result.get("personalSocialConnections"),
                })
                if activity is not None:
                    activity.step("success", "JobRight", f'Found "{job_title}" @ {company_name}')

            time.sleep(JOBRIGHT_REQUEST_DELAY_SECONDS)

        except requests.exceptions.HTTPError as e:
            cli_art.cli_error(f"HTTP error fetching position {position}: {e}")
            if e.response is not None and e.response.status_code in (401, 403):
                cli_art.cli_error("Auth error -- JobRight cookie may be expired. Stopping.")
                break
            time.sleep(JOBRIGHT_REQUEST_DELAY_SECONDS)
            continue
        except requests.exceptions.RequestException as e:
            cli_art.cli_error(f"Request error fetching position {position}: {e}")
            break

    logging.info(f"JobRight scan finished: {len(jobs)} jobs above match-score {MIN_MATCH_SCORE}.")
    return jobs
