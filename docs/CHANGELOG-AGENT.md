# Copilot Collaboration Changelog

This file tracks the work done together with GitHub Copilot on the Square360 Shared Pantheon Workflows repository.

## 2026-05-21

### Feature - `pantheon-post-deploy-drush` switches to `drush deploy` (v3.2.0)

- **Replaced separate `updb` / `cim` / `env:clear-cache` sequence with `drush deploy`** in `.github/actions/pantheon-post-deploy-drush/action.yml`
  - New canonical sequence (run inside one `terminus drush <site>.<env> -- deploy`):
    1. `updatedb --no-cache-clear` (runs `hook_update_N`)
    2. `cache:rebuild` — container sees updb's schema/state before cim
    3. `config:import`
    4. `cache:rebuild` — next request sees imported config
    5. `deploy:hook` — runs `hook_deploy_NAME` (data work that depends on imported config)
  - Then `terminus env:clear-cache` flushes Pantheon's edge/CDN cache (drush's internal cache:rebuild doesn't reach the edge)
- **Why:**
  - The previous flow ran `updb` then `cim` (or `cim` then `updb` with `[config-first]`) with no cache rebuild between them. Stale container state between the two could cause cim to misbehave — the workaround was the `[config-first]` PR-title flag. `drush deploy` fixes the underlying problem by rebuilding cache between updb and cim.
  - Adds support for `hook_deploy_NAME()` (post-config-import data migrations). Consumers writing field-to-field data migrations should now put them in `MODULE.deploy.php` rather than working around with `[config-first]` + `hook_update_N`.

### Breaking - `[config-first]` PR-title flag removed

- The `[config-first]` PR-title flag no longer does anything. The behavior it forced (cim before updb) is no longer needed — `drush deploy`'s built-in cache rebuild between updb and cim is the canonical fix.
- Consumer impact: PRs that included `[config-first]` continue to deploy, the tag is just ignored. Most existing update hooks that needed `[config-first]` will now work correctly under default ordering. The few that genuinely needed cim-first should migrate their data work to `hook_deploy_NAME()`.
- `[verbose]` PR-title flag is preserved (now passes `-v` to `drush deploy` instead of just `updb`).

### Maintenance - Self-reference bumps to v3.2.0

- **Bumped all in-repo `uses:` self-references from `@v3.1.6` to `@v3.2.0`** (18 refs) across:
  - `reusable-pantheon-deploy-dev.yml`
  - `reusable-pantheon-deploy-pr-multidev.yml`
  - `reusable-pantheon-deploy-rc-multidev.yml`
  - `reusable-pantheon-deploy-epic-multidev.yml`
- Affects: `terminus-install`, `pantheon-push`, `pantheon-post-deploy-drush`, `reusable-semantic-release.yml`, `reusable-pantheon-security-scan.yml`, `reusable-pantheon-vrt.yml`
- IDE flags these as "Unable to resolve" until the v3.2.0 tag exists — expected; semantic-release tags on merge to `main` and the diagnostics resolve themselves.

### Maintenance - Strip `[config-first]` from header comments

- Updated header/inline comments in `reusable-pantheon-deploy-dev.yml`, `reusable-pantheon-deploy-rc-multidev.yml`, `reusable-pantheon-deploy-epic-multidev.yml` to remove references to the now-removed `[config-first]` flag. `[verbose]` documentation retained.

### Out of scope (informational)

- `.github/workflows/reusable-deploy-pantheon.yml` and `.github/workflows/reusable-deploy-multidev.yml` (the older monolithic workflows still pointed to from `README.md` via `@main`) keep their existing inline `updb` / `cim` / `cr` logic. These workflows are deprecated and scheduled for removal in v4.0.0; not worth backporting drush deploy to them now.

### Release sequence (informational)

1. Merge this branch to `main` → semantic-release tags `v3.2.0`, generates root `CHANGELOG.md`, publishes GitHub release
2. Capture the v3.2.0 commit SHA from the new tag
3. Update `pantheon-github-workflows` template SHAs to point at the new tag (see that repo's CHANGELOG entry)
4. Trigger a Satis rebuild so the new release is visible to `composer update` on consumer sites

## 2026-05-20

### Feature - VRT opt-in on RC multidev (v3.1.0)

- **Added `visual_regression` job to `reusable-pantheon-deploy-rc-multidev.yml`**
  - Mirrors the PR-multidev VRT job: opt-in, post-deploy, runs against the just-built RC multidev
  - Gate: `contains(github.event.head_commit.message, '[run-vrt]') || contains(..., '[vrt]')` — the push-event equivalent of the PR-multidev's PR-body flag, since RC deploys are triggered by merge-to-`develop` and have no PR body
  - Calls `reusable-pantheon-vrt.yml` with `force_run: true` so VRT skips its own (PR-body-based) gate after we've already gated on commit message
  - Explicit secrets forwarding: `PANTHEON_MACHINE_TOKEN`, `AWS_*`, `CLICKUP_*`, `SLACK_BOT_TOKEN` — matches the cross-org pattern documented on the `security_scan` job
  - Header comment updated to document the new opt-in
  - Added `CLICKUP_API_TOKEN` and `CLICKUP_TEAM_ID` to the workflow's `secrets:` block (both optional) so the VRT job can post ClickUp comments when a task ID is present in the commit or branch

### Maintenance - Self-reference bumps to v3.1.0

- **Bumped all in-repo `uses:` self-references from `@v3.0.2` to `@v3.1.0`** across:
  - `reusable-pantheon-deploy-rc-multidev.yml`
  - `reusable-pantheon-deploy-pr-multidev.yml`
  - `reusable-pantheon-deploy-epic-multidev.yml`
  - `reusable-pantheon-deploy-dev.yml`
- Affects: `terminus-install`, `pantheon-push`, `pantheon-post-deploy-drush`, `reusable-pantheon-security-scan.yml`, `reusable-pantheon-vrt.yml`, `reusable-semantic-release.yml`
- These pins were stuck at `@v3.0.2` through hotfixes v3.0.3 / v3.0.4 / v3.0.5, so v3.1.0 also lifts the internal pins forward to current
- The IDE flags these as "Unable to resolve" until the v3.1.0 tag exists — expected; semantic-release tags on merge to `main` and the diagnostics resolve themselves

### Release sequence (informational)

1. Merge this branch to `main` → semantic-release tags `v3.1.0`, generates root `CHANGELOG.md`, publishes GitHub release
2. Capture the v3.1.0 commit SHA from the new tag
3. Update `pantheon-github-workflows` template SHAs to point at the new tag (see that repo's CHANGELOG entry)
4. Merge the plugin PR → its own semantic-release tags a new plugin version (minor — new VRT capability surfaced to consumers)

## 2025-10-23

### Added

- **Copilot Instructions File**: Created comprehensive `.github/copilot-instructions.md` with detailed guidelines for working with GitHub Actions and Pantheon workflows
  - Documented workflow patterns and conventions
  - Included pantheon-systems/push-to-pantheon@0.7.0 usage guidelines
  - Added semantic release integration patterns
  - Defined code quality standards and security considerations
  - Provided testing and maintenance guidelines
  - Created template for new workflows

- **Copilot Changelog**: Created `CHANGELOG-COPILOT.md` to track collaborative work sessions

### Research & Documentation

- **pantheon-systems/push-to-pantheon Action Versioning Analysis**
  - Researched official Pantheon repository to understand versioning strategy
  - **Key Findings:**
    - Action is in "Early Access" (pre-1.0.0) with active development
    - Default branch: `0.x`
    - Pantheon officially recommends exact version pinning (e.g., `@0.7.0`)
    - No major version tags (`@v0`) available yet
    - Breaking changes possible between minor versions
    - Input parameter names may change before 1.0.0 release
  - **Decision:** Continue using `@0.7.0` exact version pinning (aligns with Pantheon's guidance)
  - **Updated Documentation:** Enhanced copilot instructions with versioning rationale and update strategy

### Feature Implementation

- **Slack Notifications Integration**
  - Added Slack notification support to both deployment workflows
  - **New inputs added:**
    - `slack_channel`: Optional channel name for notifications (repo variable)
    - `slack_webhook_url`: Optional webhook URL for Slack integration (organization variable)
  - **Notification features:**
    - Success/failure/cancelled status with appropriate emojis and colors
    - Repository, environment, site, and status information
    - Environment URL links (when deployment succeeds)
    - Workflow run links for troubleshooting
    - Pull request links for multidev deployments
  - **Implementation approach:**
    - Used native curl commands instead of external actions for reliability
    - Added job outputs to pass environment URLs between jobs
    - Conditional logic to handle different deployment outcomes
  - **Files modified:**
    - `reusable-deploy-pantheon.yml`: Added Slack notification job
    - `reusable-deploy-multidev.yml`: Added Slack notification job
    - Added `examples/slack-notifications.yml` for usage reference
  - **Documentation updated:** Added Slack notifications section to copilot instructions

### Repository Analysis

- Analyzed existing workflow files:
  - `reusable-deploy-pantheon.yml` - Main deployment workflow with semantic release
  - `reusable-deploy-multidev.yml` - PR-based multidev deployments
  - `reusable-semantic-release.yml` - Standalone semantic release workflow
- Documented current pantheon-systems/push-to-pantheon action version (0.7.0)
- Identified key patterns for Terminus CLI usage and Drupal deployment commands
- Reviewed secret and input parameter conventions across workflows

### Context Established

- Repository serves as shared workflow library for Square360 Pantheon projects
- Workflows are designed for reusability across multiple Drupal site repositories
- Current focus on standardizing deployment patterns and semantic versioning
- Branch context: Working on `fix/semantic-release` branch

### Next Steps

- Consider updating pantheon-systems/push-to-pantheon action to newer version if available
- Evaluate workflow performance and optimization opportunities
- Consider adding additional reusable workflows for common Pantheon tasks
- Review and enhance error handling across all workflows

---

## 2025-10-30

### Feature Enhancement - Error Handling in Slack Notifications

- **Enhanced Slack Notifications with Error Reporting**
  - Added comprehensive error capture and reporting to Slack notifications
  - **New functionality:**
    - Captures specific failed step information (deployment, database updates, config import, etc.)
    - Includes detailed error messages in Slack notifications
    - Provides fallback messaging when specific error details aren't available
    - Maintains existing success notification features

- **Implementation Details:**
  - **Job Outputs Added**: Enhanced both workflows with `failed_step` and `error_message` outputs
  - **Error Capture Logic**: Added `capture_error` steps that run on deployment failure
  - **Step Identification**: Uses `steps.<step_id>.conclusion` to identify which specific step failed
  - **Conditional Error Fields**: Slack notifications dynamically include error information only when deployments fail
  - **Visual Indicators**: Failed deployments show with red color coding and ❌ emoji in Slack

- **Files Modified:**
  - `reusable-deploy-pantheon.yml`: Added error capture step and enhanced Slack notification with error fields
  - `reusable-deploy-multidev.yml`: Added error capture step and enhanced Slack notification with error fields
  - Both workflows now include contextual error messages for failed deployments

- **Error Handling Architecture:**
  - **Step-Level Detection**: Identifies failures at individual step level (push-to-pantheon, drush commands, etc.)
  - **Safe Error Capture**: Captures error context without exposing sensitive information
  - **Graceful Degradation**: Provides meaningful fallback messages when specific error details aren't captured
  - **Always-Run Notifications**: Slack notifications execute regardless of deployment outcome using `if: always()`

- **Operational Benefits:**
  - **Faster Incident Response**: Teams get immediate notification of what went wrong
  - **Reduced Troubleshooting Time**: Specific error information eliminates need to dig through GitHub Actions logs
  - **Better Visibility**: Failed deployments now provide actionable information directly in Slack
  - **Improved Reliability**: Enhanced error reporting helps maintain deployment quality

### Documentation Updates

- **Copilot Instructions Enhanced**: Error handling patterns and Slack notification architecture documented
- **Session Tracking**: Comprehensive documentation of error handling implementation approach
- **Technical Decisions**: Documented rationale for step-level error capture vs. job-level error handling

### Collaboration Context

- **Working Branch**: `fix/slack-notify` (switched from `fix/semantic-release`)
- **Session Focus**: Error handling enhancement for deployment failure scenarios
- **Implementation Approach**: Iterative development with step-by-step error capture enhancement
- **Quality Assurance**: Followed GitHub Actions best practices for conditional execution and error handling

### Technical Implementation Notes

- **Error Message Sources**: Captures errors from pantheon-systems/push-to-pantheon action and Terminus/Drush commands
- **Slack Integration**: Uses native curl commands with JSON payload construction for reliable delivery
- **Security Considerations**: Error messages filtered to prevent exposure of sensitive deployment details
- **Cross-Workflow Consistency**: Error handling patterns standardized across both deployment workflows

---

## 2025-12-03

### Feature Enhancement - Configurable Drush Command Ordering

- **Flexible Config Import and Database Update Ordering**
  - Added support for controlling the execution order of `drush cim` and `drush updb` commands
  - **Implementation approach:** Commit message tag-based detection using `[config-first]` flag
  - **Default behavior:** Database updates run first (`updb -y` → `cim -y` → `cr -y`)
  - **With [config-first]:** Config import runs first (`cim -y` → `updb -y` → `cr -y`)
  - **Visual feedback:** Workflow logs display which order is being used with 🔧 emoji indicators

- **Technical Implementation:**
  - **Priority order:** Checks PR title first, then falls back to commit message
  - **HERE document approach:** Uses bash HERE document for safe string handling of commit messages
  - **Pattern matching:** Simple substring matching with `[[ "$COMMIT_MSG" == *"[config-first]"* ]]`
  - **Cache rebuild:** Always runs last regardless of config-first flag

- **Files Modified:**
  - `reusable-deploy-multidev.yml`: Added commit message parsing and conditional drush command ordering
  - `reusable-deploy-pantheon.yml`: Added commit message parsing and conditional drush command ordering

- **Security & Robustness Enhancements:**
  - **Fixed shell escaping issues:** Resolved bash parsing errors when commit messages contain special characters
  - **Character handling improvements:**
    - ✅ Handles double quotes: `feat: Add "Show Documents" functionality`
    - ✅ Handles apostrophes: `KMHA-1947 - DR | Explore animated gif's in Drupal image library`
    - ✅ Handles mixed quotes: `fix: Update John's & Mary's contributions`
    - ✅ Handles backticks and variables: ``chore: Fix `code` blocks and $variables``
  - **Evolution of escaping approach:**
    1. **Initial attempt:** Single quotes `COMMIT_MSG='...'` (failed with apostrophes)
    2. **Second attempt:** Printf command `COMMIT_MSG=$(printf '%s' '...')` (failed with GitHub Actions interpolation timing)
    3. **Final solution:** HERE document with quoted delimiter prevents all shell expansion

       ```bash
       read -r -d '' COMMIT_MSG <<'EOF' || true
       ${{ github.event.pull_request.title || github.event.head_commit.message }}
       EOF
       ```

  - **Slack notification fixes:** Applied same escaping pattern to PR title in Slack notifications using `jq -Rs .`

### Bug Fixes

- **Commit Message Parsing Errors:**
  - **Issue:** Bash syntax errors when commit messages contained quotes or apostrophes
  - **Example error:** `unexpected EOF while looking for matching ''` with message containing `gif's`
  - **Root cause:** GitHub Actions interpolates template expressions before bash parses the script
  - **Solution:** HERE document approach with quoted EOF delimiter prevents premature expansion

- **Slack Notification JSON Injection:**
  - **Issue:** Shell parsing errors when PR titles contained quotes in Slack notification step
  - **Example error:** `command not found` when PR title contained `"Show Documents"`
  - **Solution:** Use `jq -Rs .` to properly escape PR titles before including in JSON payload
  - **Security benefit:** Prevents potential JSON injection vulnerabilities in Slack messages

### Usage Examples

**Default order (database updates first):**

```text
PR Title: "Fix styling issues and update content"
# Runs: updb -y → cim -y → cr -y
```

**Config-first order:**

```text
PR Title: "Add new field configs [config-first]"
# Runs: cim -y → updb -y → cr -y
```

**Commit message fallback:**

```text
git commit -m "Update entity types [config-first]"
# Also works if PR title doesn't contain the tag
```

### Implementation Technical Details

- **Context priority:** `github.event.pull_request.title` checked before `github.event.head_commit.message`
- **PR-centric design:** Makes sense for multidev deployments which are typically PR-triggered
- **Non-invasive:** No additional workflow inputs required, controlled entirely via commit/PR messages
- **Backward compatible:** Existing workflows without the tag continue with default behavior
- **Safe parsing:** HERE document approach is bulletproof for special character handling

### Session Context

- **Working Branch:** `fix/config-db-switch`
- **Session Focus:** Adding flexibility for Drupal deployment command ordering
- **Implementation Journey:** Multiple iterations to solve shell escaping challenges
- **Quality Focus:** Ensuring robust handling of real-world commit message edge cases

---

## 2026-03-17

### Feature - ClickUp Integration for Multidev Deployments

- **ClickUp Task Comments on Multidev Deploy**
  - Added a step to `reusable-deploy-multidev.yml` that automatically posts a comment to the linked ClickUp task when a multidev environment is created or updated
  - Task ID is extracted from the branch name or PR title using a regex pattern (e.g. `S360-835`, `NJ2P-793`)
  - Comment includes the multidev URL, environment name, site name, and a link to the PR
  - Comment distinguishes between "created" (new multidev) and "updated" (existing multidev)
  - Comment label distinguishes between "WIP Multidev" (`pr-*`), "Release Candidate Multidev" (`rc-*`), and generic "Multidev"
  - Step uses `continue-on-error: true` so ClickUp failures never block a deployment

- **Secrets passed via `pantheon-github-workflows` template**
  - Updated `workflow-configuration/templates/deploy-multidev.yml` in `pantheon-github-workflows` to pass `CLICKUP_API_TOKEN` and `CLICKUP_TEAM_ID` from org-level GitHub secrets

### Bug Fixes - ClickUp Integration

- **Terminus not installed for pre-deploy steps**
  - **Issue:** `terminus: command not found` on the `Determine source environment` and `Check if multidev environment exists` steps — terminus is only installed by `push-to-pantheon`, which runs later
  - **Fix:** Added an explicit `Install Terminus` step immediately after checkout that downloads the latest terminus phar, authenticates with `PANTHEON_MACHINE_TOKEN`, and makes terminus available for all subsequent steps

- **Multidev existence check always returning "new"**
  - **Issue:** Originally used `terminus env:list --format=list | grep -q "^<env>$"` — the grep pattern didn't reliably match the list output format
  - **Fix:** Switched to `terminus env:info <site>.<env>` which exits 0 if the environment exists and non-zero if it doesn't — no output parsing required

- **ClickUp task ID regex not matching alphanumeric prefixes**
  - **Issue:** Regex `[A-Z]+-[0-9]+` did not match IDs like `S360-835` or `NJ2P-793` where the prefix contains digits
  - **Fix:** Updated regex to `[A-Z][A-Z0-9]+-[0-9]+` to allow digits after the first letter

- **`grep` exit code causing script failure under `set -e -o pipefail`**
  - **Issue:** When no ClickUp task ID was found, `grep` returned exit code 1 which — with `pipefail` — propagated through the pipeline and killed the step
  - **Fix:** Added `|| true` to the grep pipeline to prevent non-match from being treated as a fatal error

- **Debugging added (temporary)**
  - Added `set -x`, verbose echo statements, and curl response body logging to the ClickUp step to assist with diagnosis
  - See `TODO.md` for a reminder to remove these once the integration is stable

### Files Modified

- `reusable-deploy-multidev.yml`: Terminus install step, env existence check fix, ClickUp comment step with all bug fixes applied

---

## Collaboration Notes

**Current Branch**: `fix/config-db-switch`
**Repository**: Square360/shared-pantheon-workflows
**Focus Areas**: GitHub Actions workflows, Pantheon deployment automation, Slack notifications, error handling, shell script security

**Key Technologies**: GitHub Actions, Pantheon, Terminus CLI, Drush, Semantic Release, pantheon-systems/push-to-pantheon@0.7.0, Slack Bot API, bash HERE documents, jq JSON escaping
