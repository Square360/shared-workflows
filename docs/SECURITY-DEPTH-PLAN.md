# Security scanning depth — beyond the ZAP baseline

## Context

`reusable-pantheon-security-scan.yml` runs the OWASP ZAP **baseline** action against a
pr-*/rc-* multidev (mandatory on rc-* since v4.x). Since it shipped, medium and high findings
across the fleet have been near zero. Part of that is the sites being clean; part of it is the
baseline being passive by construction: it reads responses and headers and never submits
anything, so injection, access-control and workflow flaws are outside its reach. SA-CORE-2026-013
(2026-09-16, CKEditor XSS reachable by any content editor) is the shape of finding the current
scan cannot see: it lives behind login and needs a request the baseline never makes.

This plan adds depth in four tiers, each opt-in per repo through one config file, without
changing what the baseline does today.

---

## Architecture

```
RC multidev deployed (rc-YYYY-WW) or pr-NNN
  → security job (existing trigger: --run-security label / [security] tag / mandatory on rc-*)
      → Load .github/workflow_config/security-config.yml   (new; absent = baseline only)
      → Tier 1  baseline (anonymous)            ← unchanged, always
      → Tier 2  authenticated baseline          ← if auth: block present
      → Tier 3  API scan on declared endpoints  ← if api: block present
      → Tier 4  active scan                     ← if active.enabled and env matches active.envs
      → Drupal config audit (drush)             ← if drupal_audit: true
      → Merge results → one report.json + report.html → S3 (existing layout)
      → Slack line + ClickUp comment (existing channels), tiered summary
```

Every tier is additive. A repo with no config file gets exactly today's behaviour.

---

## Config file: `.github/workflow_config/security-config.yml`

Sibling of `vrt-config.yml`; same loading pattern (repo checkout, YAML parse, defaults on
absence, warn-and-default on parse error). Schema version 1.0.

```yaml
security:
  # Tier 1 — passive baseline. Always runs; these knobs only tune it.
  baseline:
    rules_file: .github/workflow_config/zap-rules.tsv   # optional ZAP rule overrides (IGNORE/WARN/FAIL per rule id)
    max_minutes: 10                                     # -m, spider budget

  # Tier 2 — authenticated baseline. Scans as a logged-in role.
  auth:
    role: editor                        # drush user:create <role>-scan on the multidev; deleted after
    login_path: /user/login             # form-based login; ZAP context uses the session cookie
    logged_in_regex: 'Log out'          # ZAP "logged in" indicator
    exclude_paths:                      # never crawl these while authenticated
      - /user/logout
      - /admin/config/development/*
      - /admin/content/delete*

  # Tier 3 — API scan on declared endpoints (zaproxy/action-api-scan).
  api:
    openapi: null                       # path to a spec in the repo, if one exists
    endpoints:                          # otherwise a URL list; each becomes a target
      - /api/events.json
      - /jsonapi

  # Tier 4 — active scan. Fires payloads; forms get submitted. Only on scratch envs.
  active:
    enabled: false
    envs: ['rc-*']                      # glob on the target env name; never pr-* by default
    max_minutes: 60
    disable_mail: true                  # drush state:set + mail_safety config on the target before the scan
    reset_after: true                   # terminus env:clone-content live→env after the scan
    exclude_paths:
      - /user/register
      - /webform/*                      # webform submissions are real submissions; keep them out unless a repo opts in

  # Drupal-side checks ZAP cannot do. drush over Terminus, read-only.
  drupal_audit: true

  # Gate. Matches composer-audit semantics: drupal-shaped findings block at any severity.
  gate:
    fail_on: high                       # low | medium | high | critical | none
    rc_only: true                       # PR builds warn; RC builds fail
```

Repo-specific facts that belong in this file rather than in workflow inputs: the role to scan
as, the login indicator, the endpoint list, paths that must never be crawled (bulk delete
routes, real webforms), which envs may take an active scan, and the per-repo gate level.
Secrets never go here; ZAP contexts get the scan user's password from the job that created it.

---

## Tiers

### Tier 2 — authenticated baseline

The highest-value change for the least new machinery. Most of a Drupal site's attack surface
is behind login, and the RC already carries a route-smoke login, so the session plumbing exists.

1. Create a throwaway account on the target env with the configured role:
   `terminus drush <site>.<env> -- user:create scan-<run_id> --password=<random> --mail=scan@localhost`
   then `user:role:add <role>`.
2. Run the baseline action a second time with a ZAP context: form auth at `login_path`,
   `logged_in_regex` as the indicator, `exclude_paths` as context exclusions.
3. `user:cancel --delete` the account in an `always()` step.
4. Findings tagged `tier: authenticated` in report.json.

Risks: a crawl as editor can follow "delete" links. Exclusions are the guard; the default list
above blocks the bulk-delete and dev-config routes. Repos add their own.

### Tier 3 — API scan

`zaproxy/action-api-scan` against `api.openapi` or each `api.endpoints` entry. Light active
probing on JSON surfaces only (query-parameter injection, verb tampering, content-type
handling). Safe on any env; bounded by the endpoint list. Reports `tier: api`.

### Tier 4 — active scan

`zaproxy/action-full-scan`. Submits forms, follows every link, fires payloads. Never on a
pr-* env by default: those hold reviewer-staged content. On rc-* only when the repo opts in,
with mail disabled before and `env:clone-content` from live after. Budget 60 minutes. Expect
this to be quarterly per site rather than per release, triggered by `--run-active-scan` label
or `workflow_dispatch`. Reports `tier: active`.

### Drupal config audit

A drush script the workflow ships (no repo code), run over Terminus, read-only:

- text formats: which roles may use formats with `filter_html` off; CKEditor formats and
  their allowed tags
- `rest` / `jsonapi` resources enabled and their anonymous access
- anonymous permissions that should not be granted (`administer *`, `bypass node access`,
  `access content overview`, webform submission views)
- `user.settings` register mode
- modules with no maintainer / abandoned on drupal.org (composer audit covers advisories,
  not abandonment of the *installed* set)
- `system.logging` error display on non-dev envs
- trusted host patterns present

Findings map to drupal-shaped severities so the gate treats them like composer advisories.

---

## Reporting

One `report.json` (extend the VRT/security schema with a `tiers[]` array and a `tier` field
per finding) and one `report.html`. Slack line: `baseline 0/0/2 · auth 0/1/4 · api 0/0/0 ·
audit 1 high` style, with the S3 link. ClickUp comment: same summary. Existing PII-verification
step (rule 10062 against live) stays as is.

---

## Gate

Mirror the composer-audit gate that landed in v4.10 (S360-936): warn on pr-*, fail on rc-* at
`gate.fail_on` and above. Escape hatch is the same shape: `security_gate: false` workflow
input downgrades to warn-only. Drupal-audit findings block at any severity; ZAP findings at the
configured level.

---

## Phases

1. **Config loader + Tier 2 (auth).** Schema, loader, scan-user lifecycle, second baseline
   pass, `tier` in reports. Ship on one repo first (TEDCO: editor role, CKEditor formats).
2. **Drupal config audit.** The drush script and its severity mapping. Cheap, no ZAP change.
3. **Tier 3 (API).** Endpoint list first; OpenAPI when a repo has one.
4. **Gate.** Once two releases of tiered output exist and the noise floor is known.
5. **Tier 4 (active).** Last, opt-in, quarterly, after the reset-after path is proven on a
   scratch env.

---

## Open questions

- Scan-user password handoff into the ZAP context without touching the job log
  (env var from the create step; mask it).
- Whether the authenticated pass should reuse the route-smoke credentials instead of creating
  a user (simpler, but ties two jobs together and the smoke user may hold more than editor).
- Multidev capacity: an active scan holding an rc-* env for an hour blocks the next RC cut.
  Probably a dedicated `sec-scan` multidev per site, cloned from live on demand.
- Report schema bump: 1.0 → 1.1 with `tiers[]`, or a separate `security-report.json`.
