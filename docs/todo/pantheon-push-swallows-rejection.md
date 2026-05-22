# `pantheon-push` action silently succeeds when Pantheon rejects the push

**Status:** ✅ RESOLVED in v3.2.4 (2026-05-22) — implementation took Options A + B from the "Suggested fixes" section below: pre-flight SFTP-mode flip in `.github/actions/pantheon-push/action.yml`, plus a verify-after-push step that compares local HEAD to `git ls-remote` and fails the workflow loudly on mismatch. PR-comment step in `reusable-pantheon-deploy-pr-multidev.yml` also gated with `if: success()`. The bobheadxi deployment-status note in this doc was slightly off — that step lives inside the upstream action, not in our reusable workflows, so gating it would require forking upstream (deferred; not blocking the false-positive fix).
**Originally discovered:** 2026-05-22 (YH-571 session, yalehealth-yale-edu PR #126)
**Originally affected:** `Square360/shared-workflows@v3.2.2` (and all earlier 3.x — the upstream bug remains; our wrapper now defends against it)
**Blast radius:** every Square360 site that uses `pantheon-push` / `reusable-pantheon-deploy-pr-multidev.yml` / `reusable-pantheon-deploy-rc-multidev.yml` / `reusable-pantheon-deploy-epic-multidev.yml`

---

## TL;DR

When the Pantheon git remote rejects a push (pre-receive hook declined — e.g. environment in SFTP mode, branch protection on master/live, locked artifact tag, lost-update race), our `pantheon-push` composite action **reports the workflow step as successful**, the deployment record is set to `status: success`, the PR gets a green "Deploy to PR Multidev / Deploy to PR Multidev pass" check, and a "🚀 Multidev Environment Ready!" comment is posted. Pantheon never received the code.

Every downstream consequence of this is invisible until someone manually verifies. In the discovery case, `drush deploy` ran on stale code, `drush cim` re-installed a module we'd intentionally removed (because the multidev's on-disk `config/sync/core.extension.yml` was the pre-fix version), and a security finding stayed open in production for hours longer than it should have.

**This is a false-positive in CI for code deploys. It must fail loudly.**

---

## Evidence

### Workflow run that exposed the bug

Site: `yalehealth-yale-edu`
PR: <https://github.com/Square360/Yale-Health-Drupal/pull/126>
Run: <https://github.com/Square360/Yale-Health-Drupal/actions/runs/26301911705>
Job: `Deploy to PR Multidev / Deploy to PR Multidev` (job id 77429080975)
Logs (saved locally for diagnosis): `_working/github_logs/logs_70362116371/`

### The exact log lines (from the push step)

File: `_working/github_logs/logs_70362116371/Deploy to PR Multidev _ Deploy to PR Multidev/6_Push code to Pantheon multidev.txt`

Lines 783-793 (the rejection):

```
2026-05-22T17:20:30.3701  remote: Environment 'pr-126' (branch: pr-126) is currently in SFTP mode.
2026-05-22T17:20:30.3702
2026-05-22T17:20:30.3703  remote: If you are trying to push changes to a different branch or environment, try:
2026-05-22T17:20:30.3704  remote:     git push origin [branch-name]
2026-05-22T17:20:30.3705  remote: Switch connection mode to Git via the Pantheon Dashboard or Terminus:
2026-05-22T17:20:30.3707  remote:     terminus connection:set <site>.pr-126 git
2026-05-22T17:20:30.4131  To ssh://codeserver.dev.../repository.git
2026-05-22T17:20:30.4133   ! [remote rejected]     HEAD -> pr-126 (pre-receive hook declined)
2026-05-22T17:20:30.4134  error: failed to push some refs to 'ssh://codeserver.dev.../repository.git'
```

Immediately followed by (no intervening error handling):

```
2026-05-22T17:20:30.4191  ##[group]Run bobheadxi/deployments@v1
2026-05-22T17:20:30.4192  with:
2026-05-22T17:20:30.4193    status: success                                                              <-- hardcoded literal
2026-05-22T17:20:30.4194    env: pr-126
2026-05-22T17:20:30.4195    env_url: https://pr-126-yalehealth-yale-edu.pantheonsite.io
```

And then:

```
2026-05-22T17:20:32.9112  finishing deployment for 4786335224 with status success
2026-05-22T17:20:33.2651  4786335224 status set to success { statusID: 13650072219 }
```

### Independent verification

After the workflow "succeeded," we confirmed Pantheon had the OLD commit:

- GitHub's `YH-571` HEAD: `8a6a5837` (the latest, with the security fixes)
- Pantheon's `pr-126` ref: `d0212ed6` (three commits behind, no fixes deployed)

Confirmed via `git ls-remote ssh://codeserver.dev.../repository.git refs/heads/pr-126`.

Confirmed via deployed `config/sync/core.extension.yml` on the container — still listing `jsonapi: 0` (the entry we'd removed in the latest commit).

---

## Where the bug actually lives

The Square360 composite action [.github/actions/pantheon-push/action.yml](../../.github/actions/pantheon-push/action.yml) delegates the actual push to the upstream third-party action:

```yaml
- name: Push to Pantheon
  uses: pantheon-systems/push-to-pantheon@0.9.0
```

That upstream action's internal script `${GITHUB_ACTION_PATH}/scripts/main.sh push_to_pantheon` is what runs the git push and prints the rejection. It is **not** propagating the git push's non-zero exit code to the calling step.

Suspected cause inside `pantheon-systems/push-to-pantheon@0.9.0`: a `|| true`, an unchecked `$?`, or a `git push 2>&1 | tee ...` pipeline where `pipefail` is not set so the pipeline exits with the success status of `tee`. Without access to the action's source pinned at that exact SHA, the precise line is conjecture — but the symptom is unambiguous.

Square360 owns the wrapper; we don't own the upstream. So the fix has to be defensive on our side.

---

## Why the workflow has shown green for everyone, every time, until now

Two factors made this latent rather than visible:

1. **The push usually succeeds.** Most multidevs land in git mode (Pantheon's default for new envs and for envs created by the Build Tools plugin). The pre-receive hook only kicks in on SFTP-mode envs, on master/live (when the env requires a deploy not a push), and on certain tag/branch protection conditions.
2. **`pantheon-push` doesn't currently run any post-push verification.** There's no "did Pantheon actually advance to my SHA" check. So when the silent failure mode triggers, no other step in the pipeline catches it.

In the discovery case, pr-126 was inadvertently flipped to SFTP mode (likely by a contributor opening the Pantheon Dashboard's Code view, which can quietly toggle mode). Every push for hours after that silently failed; CI kept reporting green.

---

## Suggested fixes (in increasing order of effort and confidence)

### Option A — Verify-after-push (recommended, low risk)

After the `pantheon-systems/push-to-pantheon@0.9.0` step, add a verification step in our composite that:

1. Reads the local HEAD SHA we *meant* to push
2. Reads the remote ref Pantheon now has via `git ls-remote` against the Pantheon SSH URL (the SSH agent is still loaded from the push step)
3. Fails the workflow with a clear error if they don't match

Rough shape:

```yaml
- name: Verify push landed on Pantheon
  shell: bash
  env:
    SITE: ${{ inputs.site }}
    TARGET_ENV: ${{ inputs.target_env }}
  run: |
    set -euo pipefail
    LOCAL_HEAD=$(git rev-parse HEAD)
    PANTHEON_GIT_URL=$(terminus connection:info "${SITE}.${TARGET_ENV}" --field=git_url)
    REMOTE_HEAD=$(git ls-remote "${PANTHEON_GIT_URL}" "refs/heads/${TARGET_ENV}" | awk '{print $1}')
    echo "Local HEAD:    ${LOCAL_HEAD}"
    echo "Pantheon HEAD: ${REMOTE_HEAD}"
    if [[ "${LOCAL_HEAD}" != "${REMOTE_HEAD}" ]]; then
      echo "::error::Pantheon ${TARGET_ENV} is at ${REMOTE_HEAD}, expected ${LOCAL_HEAD}. The upstream push silently failed."
      echo "::error::Check the previous step's output for 'remote rejected' / 'pre-receive hook declined' / SFTP-mode notices."
      exit 1
    fi
    echo "✅ Pantheon ${TARGET_ENV} is at ${LOCAL_HEAD} as expected."
```

This catches the symptom without needing to debug or fork the upstream action. It also catches *any* future silent-fail mode in `pantheon-systems/push-to-pantheon`, not just this specific one. Belt-and-braces.

Edge cases to handle:
- The push deliberately advances Pantheon past the local HEAD (because upstream commits an artifact). Account for that: the post-stage commit we make in our action becomes the local HEAD, so the comparison is `git rev-parse HEAD` *after* the artifact commit, not the original GitHub SHA. The action.yml already commits before invoking push-to-pantheon, so `git rev-parse HEAD` at verify time is the right value.
- Multidev creation flow: when a new multidev is being created, the ref may not exist on Pantheon yet at the moment we read it. Handle the `ls-remote` returning empty as "creation in progress, accept" or wait+retry.

### Option B — Detect SFTP mode before push (preventative)

Before invoking push-to-pantheon, run:

```bash
MODE=$(terminus connection:info "${SITE}.${TARGET_ENV}" --field=connection_mode)
if [[ "${MODE}" != "git" ]]; then
  echo "::warning::${SITE}.${TARGET_ENV} is in ${MODE} mode. Flipping to git."
  terminus connection:set "${SITE}.${TARGET_ENV}" git
fi
```

Catches one specific cause of the rejection. Doesn't help with branch protection, lost-update races, or any other rejection mode. Combine with Option A.

### Option C — Patch / fork the upstream action

Replace `pantheon-systems/push-to-pantheon@0.9.0` with a Square360-owned variant (`Square360/push-to-pantheon` or vendored under `.github/actions/`) that propagates exit codes correctly. Highest effort, highest control. Worth it if the upstream is otherwise unmaintained, but Options A+B together likely give the same defensive guarantees at lower cost.

### Option D — Upstream fix (parallel track, no blocking)

File an issue at <https://github.com/pantheon-systems/push-to-pantheon> describing the swallowed exit code with the evidence above. Won't unblock Square360 in any reasonable timeframe but should land eventually.

---

## Acceptance criteria for this fix

1. A push that Pantheon rejects (any reason) **fails the GitHub Actions job** loudly. The "Deploy to PR Multidev" check goes red. No PR gets a green checkmark for a deploy that didn't actually deploy.
2. The error message names the actual cause when detectable (SFTP mode, branch protection, etc.) or directs the developer to the previous step's log otherwise.
3. The "🚀 Multidev Environment Ready!" PR comment is not posted on a failed deploy. (The current workflow may need an `if: success()` guard added on the comment step too.)
4. The GitHub deployment record (`bobheadxi/deployments@v1`) does not get set to `status: success` on a failed push — `if: success()` on that step too, or rely on `set -e` propagating from the new verify step.
5. Regression test: temporarily put a Pantheon multidev in SFTP mode, trigger the workflow, confirm the run fails with a clear actionable error.

---

## Related context for whoever picks this up

- **Affected workflow files in this repo**: `.github/workflows/reusable-pantheon-deploy-pr-multidev.yml`, `.github/workflows/reusable-pantheon-deploy-rc-multidev.yml`, `.github/workflows/reusable-pantheon-deploy-epic-multidev.yml` all use the `pantheon-push` composite.
- **The composite action**: [.github/actions/pantheon-push/action.yml](../../.github/actions/pantheon-push/action.yml). The "Push to Pantheon" step at the bottom is where the verify-after-push step should be appended.
- **Where the "Multidev Environment Ready" comment is posted**: in the reusable workflow files above (after the `pantheon-push` step). Each one has an `actions/github-script@v8` step that posts the PR comment. Add `if: success()` to that step too.
- **Where the deployment status is set to success**: `bobheadxi/deployments@v1` step, also in the reusable workflow files. The `with.status: success` is literal; the step itself runs unconditionally because there's no `if: success()` gate.
- **The yalehealth-yale-edu side workaround we're applying right now**: `terminus connection:set yalehealth-yale-edu.pr-126 git` then re-run the workflow. This unblocks PR #126 specifically but doesn't fix the workflow bug.
- **George's instruction (2026-05-22)**: GitHub is the source of record for Square360 projects; never propose direct-pushing to Pantheon as a workflow workaround. This bug, when fixed, removes one of the few legitimate reasons someone might be tempted to bypass GitHub.

---

## File this work somewhere visible

Once the fix lands, update:
- `docs/CHANGELOG-AGENT.md` and `docs/CHANGELOG.md` with the fix description and which version it landed in
- `docs/TODO.md` if it has a "known issues" section — remove the entry
- Drop a heads-up in `#client_*` Slack channels or whatever the rollout-comms surface is, so site maintainers know to expect newly-red CI on multidev/dev/test/live envs that were quietly broken until now
