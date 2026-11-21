#!/usr/bin/env python3
"""Delete stale GitHub deployment environments across the org (issue #164).

GitHub environment records only. Never touches Pantheon.

Rules:
  pr-N        delete when PR #N is closed or merged
  rc-YYYY-WW  delete when its ISO week is before the current one
  anything else (epr-*, dev, Production, copilot, open PRs, current RC) is kept

Permission checks, because GitHub answers 404 (not 403) when the token
lacks admin, which looks like "already gone":
  - repos come from the App installation, so an uncovered repo is never tried;
    repos in `also_check` that the App can't reach are reported, not attempted
  - archived repos are skipped (they refuse writes)
  - one probe before the loop: a token that can't list environments (needs
    Actions: read) fails the run once, before any repo is swept
  - a repo whose environments can't be listed is reported and skipped
  - on the first failed delete in a repo, the environment is re-read: still
    there means a permission problem, so that repo stops and the run fails;
    gone means it vanished meanwhile, so the sweep carries on

Env: GH_TOKEN, DRY_RUN ("true"/"false"), CONFIG (path to env-sweep.json),
CHAT_MESSAGE_FILE (optional: where to write the ClickUp chat message).
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
TOKEN = os.environ["GH_TOKEN"]
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
CONFIG = json.load(open(os.environ.get("CONFIG", ".github/env-sweep.json")))
EXCLUDE = {r.lower() for r in CONFIG.get("exclude", [])}
ALSO_CHECK = CONFIG.get("also_check", [])

PR_RE = re.compile(r"^pr-(\d+)$")
RC_RE = re.compile(r"^rc-(\d{4})-(\d{1,2})$")


def api(method, path):
    """Return (status, json-or-None, Link header). Never raises on HTTP errors."""
    url = path if path.startswith("http") else API + path
    req = urllib.request.Request(url, method=method, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req) as r:
                body = r.read()
                link = r.headers.get("Link", "")
                return r.status, (json.loads(body) if body else None), link
        except urllib.error.HTTPError as e:
            if e.code >= 500 and attempt == 1:
                time.sleep(3)
                continue
            return e.code, None, ""


def paged(path, key=None):
    out, url = [], f"{path}{'&' if '?' in path else '?'}per_page=100"
    while url:
        status, data, link = api("GET", url)
        if status != 200:
            return status, out
        out += data[key] if key else data
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
    return 200, out


def classify(repo, name, this_week):
    m = PR_RE.match(name)
    if m:
        status, pr, _ = api("GET", f"/repos/{repo}/pulls/{m.group(1)}")
        if status != 200:
            return "keep", f"PR #{m.group(1)} not found"
        return ("delete", f"PR #{m.group(1)} {'merged' if pr.get('merged_at') else 'closed'}") \
            if pr["state"] == "closed" else ("keep", "PR open")
    m = RC_RE.match(name)
    if m:
        week = (int(m.group(1)), int(m.group(2)))
        return ("delete", "past RC week") if week < this_week else ("keep", "current RC")
    return "keep", "not a pr-N / rc-YYYY-WW name"


def sweep(repo, this_week):
    """Return a result dict for one repo."""
    res = {"repo": repo, "deleted": [], "kept": 0, "problem": None, "fatal": False}
    status, envs = paged(f"/repos/{repo}/environments", key="environments")
    if status != 200:
        res["problem"] = f"cannot list environments (HTTP {status})"
        res["fatal"] = True
        return res
    for env in envs:
        name = env["name"]
        verdict, why = classify(repo, name, this_week)
        if verdict == "keep":
            res["kept"] += 1
            continue
        if DRY_RUN:
            res["deleted"].append(f"{name} ({why})")
            continue
        quoted = urllib.parse.quote(name, safe="")
        status, _, _ = api("DELETE", f"/repos/{repo}/environments/{quoted}")
        if status == 204:
            res["deleted"].append(f"{name} ({why})")
            time.sleep(0.2)
            continue
        recheck, _, _ = api("GET", f"/repos/{repo}/environments/{quoted}")
        if recheck == 404:
            continue  # vanished between list and delete; nothing to do
        res["problem"] = (f"delete of {name} returned HTTP {status} while the environment "
                          "still exists: the token likely lacks Administration: write here. "
                          "Stopped this repo after the first failure.")
        res["fatal"] = True
        return res
    return res


def main():
    iso = datetime.date.today().isocalendar()
    this_week = (iso[0], iso[1])

    status, installed = paged("/installation/repositories", key="repositories")
    if status != 200:
        msg = f"Cannot list the App installation's repositories (HTTP {status})."
        print(f"::error::{msg}")
        fail_chat(msg)
        return 1
    by_name = {r["full_name"].lower(): r for r in installed}

    results, skipped, targets = [], [], []
    for r in sorted(installed, key=lambda r: r["full_name"].lower()):
        name = r["full_name"]
        if name.lower() in EXCLUDE:
            skipped.append((name, "excluded in env-sweep.json"))
        elif r.get("archived"):
            skipped.append((name, "archived (refuses writes)"))
        else:
            targets.append(name)

    # Permission check: one probe before the loop, so a token that can't read
    # environments fails once with a clear message instead of once per repo.
    if targets:
        status, _, _ = api("GET", f"/repos/{targets[0]}/environments?per_page=1")
        if status in (403, 404):
            msg = (f"The App token cannot list environments (HTTP {status} on "
                   f"{targets[0]}). Listing needs the App's Actions: read permission; "
                   "deleting needs Administration: write.")
            print(f"::error::{msg}")
            fail_chat(msg)
            return 1
    for name in targets:
        results.append(sweep(name, this_week))
    for name in ALSO_CHECK:
        if name.lower() not in by_name:
            skipped.append((name, "App not installed there: needs that repo's owner to clean up"))

    mode = "DRY RUN: nothing deleted" if DRY_RUN else "deleting"
    verb = "Would delete" if DRY_RUN else "Deleted"
    total = sum(len(r["deleted"]) for r in results)
    lines = [f"## Stale environment sweep ({mode})", "",
             f"ISO week {this_week[0]}-{this_week[1]:02d}. {verb} **{total}** across "
             f"{len(results)} repos.", "",
             f"| Repo | {verb} | Kept | Problem |", "|---|---:|---:|---|"]
    for r in results:
        if r["deleted"] or r["problem"]:
            lines.append(f"| {r['repo']} | {len(r['deleted'])} | {r['kept']} | {r['problem'] or ''} |")
    quiet = [r for r in results if not r["deleted"] and not r["problem"]]
    if quiet:
        lines += ["", f"{len(quiet)} repos had nothing stale."]
    if skipped:
        lines += ["", "**Skipped**", ""] + [f"- {n}: {why}" for n, why in skipped]
    detail = [r for r in results if r["deleted"]]
    if detail:
        lines += ["", "<details><summary>Environment names</summary>", ""]
        for r in detail:
            lines.append(f"**{r['repo']}**: " + ", ".join(r["deleted"]))
            lines.append("")
        lines.append("</details>")
    report = "\n".join(lines) + "\n"
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(report)

    fatal = [r for r in results if r["fatal"]]
    for r in fatal:
        print(f"::error title={r['repo']}::{r['problem']}")
    write_chat(results, fatal, total, verb)
    return 1 if fatal else 0


def write_chat(results, fatal, total, verb):
    """Short ClickUp chat message; empty (no post) when nothing happened."""
    path = os.environ.get("CHAT_MESSAGE_FILE")
    if not path or (total == 0 and not fatal):
        return
    run = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
           f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}")
    head = f"**Stale GitHub environment sweep**: {verb.lower()} {total}"
    per = [f"{r['repo'].split('/')[-1]} {len(r['deleted'])}" for r in results if r["deleted"]]
    lines = [head + (f" ({', '.join(per)})" if per else "") + "."]
    for r in fatal:
        lines.append(f"- Problem on `{r['repo']}`: {r['problem']}")
    lines.append(f"[Run summary]({run})")
    open(path, "w").write("\n".join(lines) + "\n")


def fail_chat(message):
    """Run-level failure (token can't list, installation unreadable)."""
    path = os.environ.get("CHAT_MESSAGE_FILE")
    if path:
        run = (f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/"
               f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}")
        open(path, "w").write(f"**Stale GitHub environment sweep failed**: {message}\n[Run]({run})\n")


if __name__ == "__main__":
    sys.exit(main())
