#!/usr/bin/env python3
"""Daily Drupal security watch (issue #187).

Posts Critical / Highly Critical advisories to the ClickUp Development channel:
  - drupal.org core advisories at those levels, with the sites still exposed
  - contrib (and other package) advisories at those levels, only when one of
    our sites' default-branch lock files is exposed
  - every drupal.org PSA (advance notice of core / contrib release windows)
Moderately critical and below ride routine releases and are never posted.

Exposure comes from `composer audit --locked` on each repo's composer.lock,
fetched read-only through the Square360 Security Watch App. Each advisory or
PSA posts once; posted keys live in STATE_FILE (kept in the Actions cache).

Env: GH_TOKEN, CONFIG (env-sweep.json: `exclude` is shared with the
environment sweep; `security_watch_exclude` applies here only), STATE_FILE, CHAT_MESSAGE_FILE,
DRY_RUN ("true" prints only).
"""
import datetime
import email.utils
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

API = "https://api.github.com"
TOKEN = os.environ["GH_TOKEN"]
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"
CONFIG = json.load(open(os.environ.get("CONFIG", ".github/env-sweep.json")))
EXCLUDE = {r.lower() for r in CONFIG.get("exclude", []) + CONFIG.get("security_watch_exclude", [])}
STATE_FILE = os.environ.get("STATE_FILE", "security-watch-state.json")
FEED_WINDOW_DAYS = 14   # feed items older than this are never posted (bounds a lost cache)

FEEDS = {
    "core": "https://www.drupal.org/security/rss.xml",
    "contrib": "https://www.drupal.org/security/contrib/rss.xml",
    "psa": "https://www.drupal.org/security/psa/rss.xml",
}
# Drupal puts the risk level in the title: "Webform - Critical - Remote code execution - SA-…"
SEVERE = re.compile(r"\s-\s(Highly critical|Critical)\s-\s", re.I)
UA = "square360-security-watch (+https://github.com/Square360/shared-workflows)"


def http(url, headers=None, raw=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            return r.status, (body if raw else json.loads(body)), r.headers.get("Link", "")
    except urllib.error.HTTPError as e:
        return e.code, None, ""


def gh(path, raw=False):
    accept = "application/vnd.github.raw" if raw else "application/vnd.github+json"
    return http(path if path.startswith("http") else API + path,
                {"Authorization": f"Bearer {TOKEN}", "Accept": accept,
                 "X-GitHub-Api-Version": "2022-11-28"}, raw=raw)


def installed_repos():
    out, url = [], f"{API}/installation/repositories?per_page=100"
    while url:
        status, data, link = gh(url)
        if status != 200:
            raise SystemExit(f"Cannot list the App installation's repositories (HTTP {status}).")
        out += data["repositories"]
        m = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = m.group(1) if m else None
    return out


def severe(title, severity, package=""):
    """Critical / Highly Critical by Drupal's label. drupal/* counts only by that label
    (Packagist mirrors the same advisory under a GHSA id, which would post twice);
    other libraries count when the GHSA severity is 'critical'."""
    if SEVERE.search(title or ""):
        return True
    if package.startswith("drupal/"):
        return False
    return (severity or "").lower() == "critical"


def audit_repo(repo, branch):
    """Return (list of advisories, problem). Lock file read via the API, audited offline from the repo."""
    # Sites only: a Pantheon site has pantheon.yml at the root. Themes, modules
    # and retired repos with a stray lock file would otherwise post as exposed.
    if gh(f"/repos/{repo}/contents/pantheon.yml?ref={branch}")[0] != 200:
        return None, None
    status, lock, _ = gh(f"/repos/{repo}/contents/composer.lock?ref={branch}", raw=True)
    if status == 404:
        return None, None          # no lock file at the root
    if status != 200:
        return None, f"cannot read composer.lock (HTTP {status})"
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/composer.lock", "wb").write(lock)
        # A minimal composer.json: the audit reads packages from the lock and
        # advisories from Packagist plus drupal.org, and never touches the
        # site's private repositories.
        json.dump({"repositories": [{"type": "composer", "url": "https://packages.drupal.org/8"}]},
                  open(f"{d}/composer.json", "w"))
        # --no-dev: deploys run `composer install --no-dev`, so require-dev
        # packages never reach Pantheon and aren't exposure.
        r = subprocess.run(["composer", "audit", "--locked", "--no-dev", "--format=json",
                            "--no-interaction", "--no-plugins", "--abandoned=ignore"],
                           cwd=d, capture_output=True, text=True, timeout=180)
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return None, f"composer audit failed: {(r.stderr or r.stdout).strip()[:200]}"
    advisories = data.get("advisories") or {}
    out = []
    for pkg, items in advisories.items():
        for a in (items.values() if isinstance(items, dict) else items):
            out.append({"package": pkg, "id": a.get("advisoryId"), "title": a.get("title", ""),
                        "severity": a.get("severity"), "link": a.get("link"),
                        "affected": a.get("affectedVersions", "")})
    return out, None


def read_feed(kind, url):
    status, body, _ = http(url, raw=True)
    if status != 200:
        return None
    items = []
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=FEED_WINDOW_DAYS)
    for it in ET.fromstring(body).iter("item"):
        title, link = it.findtext("title") or "", it.findtext("link") or ""
        try:
            when = email.utils.parsedate_to_datetime(it.findtext("pubDate"))
        except (TypeError, ValueError):
            continue
        if when < cutoff:
            continue
        m = re.search(r"((?:SA-CORE|SA-CONTRIB|PSA)-[\d-]+)\s*$", title)
        items.append({"kind": kind, "id": m.group(1) if m else link, "title": title, "link": link})
    return items


def main():
    state = set()
    if os.path.exists(STATE_FILE):
        state = set(json.load(open(STATE_FILE)).get("posted", []))
    problems = []

    # Exposure across the portfolio: advisory id -> {meta, sites}
    exposure = {}
    repos = [r for r in installed_repos()
             if r["full_name"].lower() not in EXCLUDE and not r.get("archived")]
    for r in sorted(repos, key=lambda r: r["full_name"].lower()):
        found, problem = audit_repo(r["full_name"], r["default_branch"])
        if problem:
            problems.append(f"{r['full_name']}: {problem}")
        for a in found or []:
            if not severe(a["title"], a["severity"], a["package"]):
                continue
            key = a["id"] or f"{a['package']}:{a['title']}"
            e = exposure.setdefault(key, {**a, "sites": []})
            e["sites"].append(r["name"])

    feed = []
    for kind, url in FEEDS.items():
        items = read_feed(kind, url)
        if items is None:
            problems.append(f"drupal.org {kind} feed unreachable")
        else:
            feed += items

    posts = []
    # Core advisories at Critical / Highly Critical: post with exposure (none exposed is still news).
    for it in feed:
        if it["kind"] == "core" and SEVERE.search(it["title"]) and it["id"] not in state:
            sites = exposure.get(it["id"], {}).get("sites", [])
            posts.append((it["id"], f"**{it['title']}**: {it['link']}\n"
                          + (f"Still exposed: {', '.join(sorted(sites))}" if sites
                             else "No default branch is exposed (already patched, or not yet in the audit data).")))
    # PSAs: always (they announce release windows).
    for it in feed:
        if it["kind"] == "psa" and it["id"] not in state:
            posts.append((it["id"], f"**{it['title']}**: {it['link']}"))
    # Package advisories with real exposure (contrib and non-Drupal libraries).
    core_ids = {it["id"] for it in feed if it["kind"] == "core"}
    for key, e in sorted(exposure.items()):
        if key in state or key in core_ids:
            continue
        posts.append((key, f"**{e['title']}** ({e['package']} {e['affected']}): {e['link'] or ''}\n"
                      f"Exposed: {', '.join(sorted(e['sites']))}"))

    lines = [f"## Security watch ({'DRY RUN: nothing posted' if DRY_RUN else 'live'})", "",
             f"Audited {len(repos)} repos. {len(exposure)} Critical/Highly Critical advisories exposed; "
             f"{len(posts)} new to post.", ""]
    lines += [f"- {body.splitlines()[0]}" for _, body in posts]
    if problems:
        lines += ["", "**Problems**", ""] + [f"- {p}" for p in problems]
    report = "\n".join(lines) + "\n"
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(report)

    if posts and os.environ.get("CHAT_MESSAGE_FILE"):
        msg = "**Drupal security watch**\n\n" + "\n\n".join(body for _, body in posts)
        open(os.environ["CHAT_MESSAGE_FILE"], "w").write(msg + "\n")
    if not DRY_RUN:
        state |= {k for k, _ in posts}
        json.dump({"posted": sorted(state)}, open(STATE_FILE, "w"), indent=1)
    for p in problems:
        print(f"::warning::{p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
