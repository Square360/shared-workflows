# Visual Regression Testing (VRT) with Playwright

## Context

The shared-pantheon-workflows system deploys PRs as multidev environments — `pr-NNN` for open PRs
and `rc-YYYY-WW` for PRs merged to `develop`. VRT can run after either type of deploy. It is
opt-in via a `[vrt]` tag in the PR description. Optionally, a ClickUp Custom ID can be included —
e.g. `[vrt YMAC-959]` — to also post the results as a comment on that ticket. If no task ID is
explicit in the tag, the branch name is scanned as a fallback (e.g. `feature/ymac-959-my-feature`
→ `YMAC-959`).

---

## Architecture Overview

```
PR merged to develop
  → RC multidev deployed (rc-2025-12)
  → VRT job triggered (if [vrt] or [vrt TASK-ID] in PR body)
      → Extract optional ClickUp Custom ID from tag
      → Load .github/workflows/vrt-config.yml from repo
      → Get LIVE URL via Terminus
      → Playwright: screenshot LIVE + RC for each configured path
      → pixelmatch: diff screenshots
      → Upload screenshots + diff images + HTML report → S3
      → Comment on PR with pass/fail summary + S3 report link
      → If ClickUp task ID present: post same summary as comment on that task
```

---

## Files to Create / Modify

### 1. New reusable workflow (shared-pantheon-workflows)
**Path:** `.github/workflows/reusable-visual-regression.yml`

**Inputs:**
- `pantheon_site` (required) — site machine name
- `multidev_url` (required) — RC multidev URL (passed from deploy job output)
- `target_env` (required) — RC env name (e.g., `rc-2025-12`)
- `slack_channel` (optional)

**Secrets:**
- `PANTHEON_MACHINE_TOKEN` (required) — to get LIVE URL via Terminus
- `AWS_ACCESS_KEY_ID` (required)
- `AWS_SECRET_ACCESS_KEY` (required)
- `AWS_S3_BUCKET` (required) — bucket name
- `AWS_S3_REGION` (optional, default `us-east-1`)
- `CLICKUP_API_TOKEN` (optional) — required only when posting results to a ClickUp task

**Steps:**

1. Parse `github.event.pull_request.body` with regex `\[vrt(?:\s+([A-Z]+-\d+))?\]` — exit early if no match; capture optional ClickUp Custom ID (e.g. `YMAC-959`) into `CLICKUP_TASK_ID`
2. Checkout repo to read `vrt-config.yml`
3. Install Terminus; get LIVE URL via `terminus env:view {site}.live --print`
4. Install Node.js + Playwright + pixelmatch
5. Read `.github/workflows/vrt-config.yml`; for each path:
   - Screenshot LIVE URL + path → `live/{slug}.png`
   - Screenshot RC URL + path → `rc/{slug}.png`
   - Diff with pixelmatch → `diff/{slug}.png`, record pixel diff %
6. Generate `report.html` summarizing pass/fail per page with inline images
7. Upload entire run folder to S3 under `{pantheon_site}/{run_id}/`
8. Comment on PR with summary table and link to S3 report
9. If `CLICKUP_TASK_ID` was captured and `CLICKUP_API_TOKEN` is set: post the same summary as a comment on that ClickUp task via the REST API (`POST /task/{custom_id}/comment?custom_task_ids=true`)
10. Optionally notify Slack

### 2. Update deploy-multidev.yml template (pantheon-github-workflows)
**Path:** `workflow-configuration/templates/deploy-multidev.yml`

Add a new job `visual_regression_test` after `deploy_multidev`:

```yaml
visual_regression_test:
  name: Visual Regression Test
  needs: [deploy_multidev, calculate_target_env]
  # Only run for RC environments (merged to develop)
  if: |
    startsWith(needs.calculate_target_env.outputs.target_env, 'rc-') &&
    needs.deploy_multidev.result == 'success'
  uses: Square360/shared-pantheon-workflows/.github/workflows/reusable-visual-regression.yml@main
  with:
    pantheon_site: ${{ vars.PANTHEON_SITE }}
    multidev_url: ${{ needs.deploy_multidev.outputs.multidev_url }}
    target_env: ${{ needs.calculate_target_env.outputs.target_env }}
    slack_channel: ${{ vars.SLACK_CHANNEL }}
  secrets:
    PANTHEON_MACHINE_TOKEN: ${{ secrets.PANTHEON_MACHINE_TOKEN }}
    AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
    AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
    AWS_S3_BUCKET: ${{ secrets.AWS_S3_BUCKET }}
    CLICKUP_API_TOKEN: ${{ secrets.CLICKUP_API_TOKEN }}
```

### 3. VRT config schema (per-repo, NOT managed by the composer plugin — preserved)
**Path in each consuming repo:** `.github/workflow_config/vrt-config.yml`

```yaml
vrt:
  threshold: 0.05        # Max acceptable diff ratio (0.0–1.0); default 0.05
  fail_on_diff: false    # Whether to fail the workflow job on threshold breach
  wait: 6                # Default seconds to wait after networkidle before screenshotting; default 6
  bypass_header: x-pantheon-bot-bypass  # Header carrying the site's AGCDN bot-bypass token (token lives in 1Password: s360-cicd/pantheon-bot-bypass/<site>); default shown
  viewports:
    - width: 1440
      height: 900
      name: desktop
    - width: 390
      height: 844
      name: mobile
  pages:
    - path: /
      name: homepage
    - path: /about
      name: about-us
    - path: /contact
      name: contact
      wait: 12           # Per-page override — useful for pages with heavy animations or lazy-loaded content
```

---

## AWS Infrastructure

### S3 Bucket Structure

Single shared bucket, organized by site:

```
s3://your-vrt-bucket/
  {pantheon_site}/
    {target_env}-{github_run_id}-{run_attempt}/
      live/
        homepage-desktop.png
        homepage-mobile.png
      rc/
        homepage-desktop.png
        homepage-mobile.png
      diff/
        homepage-desktop.png   ← red pixels highlight differences
        homepage-mobile.png
      report.html
```

### IAM Setup (one-time, you create in AWS Console)

1. Create S3 bucket: `square360-vrt-reports` (or similar)
2. Create IAM user `github-vrt-bot` with inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:PutObject", "s3:GetObject", "s3:ListBucket"],
    "Resource": [
      "arn:aws:s3:::square360-vrt-reports",
      "arn:aws:s3:::square360-vrt-reports/*"
    ]
  }]
}
```

3. Bucket policy: make `*/report.html` and `*/diff/*` publicly readable so PR comment links work without signing.
4. Store IAM access key + secret as GitHub org-level secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_S3_BUCKET`

### Playwright Script

Inline Node.js script in the reusable workflow (no separate repo needed):
- Uses `@playwright/test` + `pixelmatch` + `pngjs` npm packages
- Installed at runtime with `npm install --no-save`
- Script is written to a temp file in the workflow

---

## Key Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| LIVE as baseline | LIVE site IS the reference | No separate baseline storage/sync needed |
| [vrt] in PR body | Not title — more space | Consistent with [config-first] pattern in titles |
| Any multidev type | No `rc-` restriction | Teams need VRT on WIP `pr-NNN` envs too; `[vrt]` tag is the gate |
| ClickUp task ID in tag | `[vrt TASK-123]` syntax | Zero extra config; ID is co-located with the trigger |
| ClickUp ID branch fallback | Scan `head_ref` if no explicit ID | Branch names (e.g. `ymac-959-my-feature`) already carry the task ID |
| ClickUp comment API | Custom ID endpoint + `custom_task_ids=true` | Works with the human-readable IDs teams already use |
| CLICKUP_API_TOKEN optional | No-op if absent | ClickUp integration doesn't break repos that haven't configured it |
| Extra pages in PR body | `[vrt-pages]...[/vrt-pages]` block | Per-PR ad-hoc paths (e.g. seasonal promos) without touching vrt-config.yml |
| S3 report | Self-contained HTML (base64 screenshots) | Single public URL; no S3 path complexity for live/rc images |
| fail_on_diff default | false (warn only) | VRT informs; teams opt-in to hard failure via `fail_on_diff: true` |
| fail_on_diff timing | Assert step runs last | S3 upload and PR/ClickUp comments post even when the job ultimately fails |
| Viewports | Desktop (1440×900) + Mobile (390×844) | Both captured by default; overridable per repo |
| Auth | Anonymous/public pages only | No credential complexity; covers all marketing/content pages |
| Playwright + pixelmatch | Industry standard | Well-maintained, Chromium headless, pixel-accurate diffs |

---

## Verification / Testing Plan

1. Create a test repo with the updated `deploy-multidev.yml` template
2. Add `.github/workflows/vrt-config.yml` with 2–3 test URLs
3. **Basic VRT on PR multidev** — open a PR with `[vrt]` in the body (no task ID); confirm:
   - `pr-NNN` multidev deploys as normal
   - VRT job starts after deploy
   - Self-contained `report.html` uploaded to S3
   - PR comment includes summary table + report link
4. **Basic VRT on RC** — merge the PR to `develop`; confirm same behaviour for `rc-YYYY-WW`
5. **Diff detection** — intentionally introduce a visual change; confirm diff images highlight it
6. **Skip when no tag** — open a PR without `[vrt]`; confirm VRT job starts but exits at the parse step (all steps skipped)
7. **Explicit ClickUp ID** — use `[vrt YMAC-959]`; confirm comment appears on that ClickUp task
8. **Branch name ClickUp fallback** — use `[vrt]` on a branch named `feature/ymac-959-my-feature`; confirm same ClickUp comment without explicit ID in tag
9. **Extra pages** — include a `[vrt-pages]` block with 2 ad-hoc paths; confirm those pages are tested in addition to `vrt-config.yml` paths
10. **No ClickUp secrets** — use `[vrt TASK-123]` but omit `CLICKUP_API_TOKEN`; confirm workflow completes without error
11. **fail_on_diff** — set `fail_on_diff: true` in `vrt-config.yml` and introduce a diff; confirm PR comment and S3 upload still happen before the job fails
