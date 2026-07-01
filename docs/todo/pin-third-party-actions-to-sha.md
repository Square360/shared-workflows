# Third-party GitHub Actions are tag-pinned, not SHA-pinned (supply-chain exposure)

**Status:** 🔴 OPEN
**Originally discovered:** 2026-06-11 (Shield OWASP sweep of griefsensitivehealthcare, branch YGSH-310)
**Affected:** every workflow and composite action in this repo, plus the consumer-side workflow templates distributed via `square360/pantheon-github-workflows`
**Blast radius:** every Square360 site consuming these workflows — the actions run with repo secrets context (Terminus machine tokens, SSH keys, GitHub tokens)

---

## TL;DR

Every third-party action reference in this repo uses a moving tag (`@v6`, `@v2`, `@0.9.0`) instead of a commit SHA. A moving tag can be re-pointed at malicious code by anyone who compromises the action's repo — the consumer never sees a diff. This is the exact mechanism of the March 2025 `tj-actions/changed-files` compromise, where a re-tagged release exfiltrated CI secrets from thousands of repos.

The irony: consumer repos already reference *our* reusable workflows by full SHA (`Square360/shared-workflows/.github/workflows/...@94d15bab... # v3.2.6`). The convention exists and is followed for the Square360 layer — it just stops there. The third-party layer underneath is unpinned in both this repo and the consumer templates.

## Inventory (as of 2026-06-11)

In this repo (`.github/workflows/` + `.github/actions/`), by reference count:

| Action | Refs | Owner | Risk note |
|---|---|---|---|
| `actions/checkout@v6` | 11 | GitHub | lower practical risk, same rule |
| `actions/github-script@v8` (+1 `@v7`) | 7 | GitHub | runs arbitrary JS with token |
| `shivammathur/setup-php@v2` | 3 | community | **single-maintainer, sees secrets context** |
| `pantheon-systems/push-to-pantheon@0.9.0` | 3 | vendor | version tag, still movable |
| `actions/cache@v5` | 3 | GitHub | |
| `zaproxy/action-baseline@v0.14.0` | 2 | community | |
| `actions/setup-node@v4` / `@v6` | 3 | GitHub | inconsistent major, while we're in here |

Consumer-side templates (distributed by `square360/pantheon-github-workflows` into site repos as `deploy-multidev.yml` / `deploy-to-dev.yml`):

- `marocchino/sticky-pull-request-comment@v3` — community-owned, posts PR comments with token
- `shivammathur/setup-php@v2`
- `actions/checkout@v6`

`grep -rhoE 'uses: [^ ]+@[a-f0-9]{40}'` over this repo returns **nothing** — zero SHA-pinned references today.

## Fix

Pin every `uses:` reference to the full 40-char commit SHA of its current release, with the human-readable tag in a trailing comment — the same convention consumers already use for our reusables:

```yaml
# before
uses: shivammathur/setup-php@v2
# after
uses: shivammathur/setup-php@9e72090525849c5e82e596468b86eb55e9cc5401 # v2.30.0
```

Order of attack:

1. **Community-owned actions first** (`shivammathur/setup-php`, `marocchino/sticky-pull-request-comment`, `zaproxy/action-baseline`) — highest exposure, fewest refs.
2. `pantheon-systems/push-to-pantheon` — vendor-owned but see `pantheon-push-swallows-rejection.md`; we already distrust its release hygiene.
3. `actions/*` (GitHub-owned) — lower urgency, do in the same pass for a uniform rule.
4. The consumer templates in `square360/pantheon-github-workflows` — same treatment, ships to sites on their next `composer update` (that repo cuts releases per-commit; the change must go out as `fix():`, not `docs():`).

Maintenance: SHA pins freeze updates, so add Dependabot (`package-ecosystem: github-actions`) to this repo and to `pantheon-github-workflows` — it bumps the SHA *and* the comment in a reviewable PR, which is the whole point.

## Acceptance criteria

1. `grep -rE 'uses: [^.@]+@v?[0-9]' .github/ | grep -v Square360/` returns nothing in this repo (every external ref is a 40-char SHA + comment).
2. Same check passes on the templates in `square360/pantheon-github-workflows`.
3. Dependabot config for `github-actions` ecosystem exists in both repos.
4. A consumer site regenerates its workflows via `composer update` and the multidev pipeline still passes end-to-end.
