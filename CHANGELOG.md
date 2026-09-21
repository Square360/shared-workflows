# Release 4.11.2 (2026-09-21)

### Documentation

* contributing: find the callers before editing a reusable; nested calls use @v4, never a SHA; test via a client caller pointed at the branch (4389a4c)

### Chores

* remove the deprecated monolithic workflows, unreferenced variants, stale examples and finished plans; rewrite README to the v4 layout (5c6613f)

# Release 4.11.1 (2026-09-21)

### Bug Fixes

* vrt: read the bot-bypass token from Terminus so a missing 1Password field stops killing VRT (2898532)

# Release 4.11.0 (2026-09-17)

### Features

* S360-1077: ZAP + VRT write their results to the GitHub job summary; ClickUp comments opt-in (5c5b8f3)

### Bug Fixes

* S360-1082: call reusable-route-smoke from the multidev workflows at the v4 moving tag (was the v4.8.2 SHA), so the advban self-unban fix reaches RC builds (7b38e14)
* S360-1076: port the backup verify-by-listing to reusable-pantheon-deploy-dev.yml, the workflow the fleet actually calls (74a7051)
* rc-multidev: skip GitHub-inferred merges and serialise RC deploys per site (b23ce20)
* S360-1076: verify the LIVE backup by listing instead of trusting terminus's exit code (27a966f)
* route-smoke: unban the runner's egress IP before checking routes (9913f17)

### Documentation

* release-prep config for this repo (first run, S360-1080) (9a32e96)

# Release 4.10.2 (2026-09-16)

### Bug Fixes

* vrt: call reusable-pantheon-vrt from the multidev workflows at the v4 moving tag instead of the v4.3.0 SHA (cef277b)
* vrt: send the per-site Pantheon bot-bypass header so the AGCDN challenge stops timing out every screenshot (34359d4)

# Release 4.10.1 (2026-09-03)

### Bug Fixes

* rc-multidev: audit composer.lock with --locked — gate job has no vendor/ (e41b57e)

# Release 4.10.0 (2026-09-03)

### Features

* rc-multidev: composer audit gate — fail the release candidate on drupal/* advisories (a406b2a)

### Bug Fixes

* honour --docs-only / --skip-multidev on RC and DEV deploys; a semantic release always deploys (a90fc47)

# Release 4.9.1 (2026-08-20)

### Bug Fixes

* authenticate the Terminus version lookup — unauthenticated api.github.com rate-limits on shared runners (6aa4294)

# Release 4.9.0 (2026-08-19)

### Features

* reusable-composer-diff — sticky PR comment for composer.lock changes (256814d)

### Bug Fixes

* bump nested route-smoke pins to v4.8.2 so the uli vars fallback is reachable (2421706)

# Release 4.8.2 (2026-08-19)

### Bug Fixes

* route-smoke: resolve uli account from ROUTE_SMOKE_ULI_OPTIONS repo/org variable (95bb525)

### Chores

* drop unrelated local diagram assets accidentally committed (4173ed1)

# Release 4.8.1 (2026-08-19)

### Bug Fixes

* retry transient network failures on every Terminus fetch (cb3fb43)

# Release 4.8.0 (2026-08-19)

### Features

* pr-multidev: php-quality + route-smoke built into the PR multidev flow (4315800)

# Release 4.7.0 (2026-08-19)

### Features

* rc: route-smoke gates the RC security scan (bc20977)

# Release 4.6.0 (2026-08-19)

### Features

* failure-only Slack notification (slack_channel input) (1026990)
* reusable route-smoke workflow — authenticated key-route checks via drush uli (5b6e70e)

### Bug Fixes

* retry + report login-curl TLS failures, stage timing echoes (2e4f97d)
* load Pantheon SSH key — terminus drush runs over SSH, machine token is not enough (8deb8c2)
* surface drush uli stderr on failure, curl --max-time 30, job timeout-minutes 10 (227b6a5)

### Documentation

* add /admin/structure/menu to recommended smoke routes (08b6c01)

# Release 4.5.0 (2026-08-19)

### Features

* reusable PHP quality workflow — plugin class-load check + custom unit tests (87f266d)

### Bug Fixes

* block-scalar the skip notice — colon-space in a plain run scalar is a YAML syntax error (cd9e741)

# Release 4.4.3 (2026-08-18)

### Bug Fixes

* verify ZAP PII (10062) findings against live pages before the severity gate (523d079)

# Release 4.4.2 (2026-08-18)

### Bug Fixes

* install release tooling in an isolated prefix (f4bfee5)

# Release 4.4.1 (2026-08-18)

### Bug Fixes

* ignore workspaces when installing semantic-release tooling (7e2a97f)

# Release 4.4.0 (2026-08-18)

### Features

* maintain moving major-version tags (v4, v5, …) on release (c504b13)

# Release 4.3.2 (2026-08-18)

### Bug Fixes

* gate npm ci on package-lock.json, not package.json (825af59)

# Release 4.3.1 (2026-08-11)

### Bug Fixes

* pin internal refs to v4.3.0 so the settle gates are reachable (e609935)

# Release 4.3.0 (2026-08-11)

### Features

* gate drush deploy on platform workflows, tree consistency, and files-mount readiness (f756cee)

### Bug Fixes

* raise settle-gate ceilings to 6min for large sites (81a519e)

# Release 4.2.3 (2026-08-11)

### Bug Fixes

* bump internal self-ref pins so shipped fixes actually run (529093f)

# Release 4.2.2 (2026-08-11)

### Bug Fixes

* bump node20-era action pins to node24-ready releases (69eaf3a)

# Release 4.2.1 (2026-07-18)

### Bug Fixes

* VRT reusable ignores the --run-vrt label its callers accept (0efd3ac)

# Release 4.2.0 (2026-07-18)

### Features

* double-hyphen label convention (--run-vrt et al) for picker grouping (91904ad)
* label-based opt-ins for VRT, security scan, and multidev skip flags (fb7eda0)

# Release 4.1.4 (2026-07-18)

### Bug Fixes

* RC multidev VRT opt-in never fires on merged-PR triggers (17b9783)

# Release 4.1.3 (2026-07-11)

### Bug Fixes

* pantheon: bump internal composite-action refs to v4.1.2 (1bd4fce)

# Release 4.1.2 (2026-07-11)

### Bug Fixes

* pantheon: wait for pushed commit to reach env filesystem before drush deploy (a9de69c)

# Release 4.1.1 (2026-07-01)

### Bug Fixes

* vrt: pin js-yaml to v4 and use named import (9b6c2ee)

# Release 4.1.0 (2026-06-16)

### Features

* add semantic-release workflow (6058d2d)

### Bug Fixes

* add /vrt/ prefix to S3 key paths in reusable-pantheon-vrt (b753308)
* migrate reusable-satis-publish to 1Password secrets (53eb8d8)
