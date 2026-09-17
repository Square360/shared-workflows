# Square360 Shared Workflows

Reusable GitHub Actions workflows and composite actions for Square360's Pantheon-hosted Drupal sites. Client repos do not call these directly: the `square360/pantheon-github-workflows` Composer plugin installs two thin callers (`deploy-to-dev.yml`, `deploy-multidev.yml`) that reference the reusables below at the `v4` moving major tag.

## Reusable workflows (`.github/workflows/`)

| Workflow | Runs when | Does |
|---|---|---|
| `reusable-pantheon-deploy-dev.yml` | release PR merges to master/main | semantic-release, push to DEV, LIVE backup (verified by listing), `drush deploy`, Slack |
| `reusable-pantheon-deploy-pr-multidev.yml` | PR opened/updated | `pr-NNN` multidev, php-quality, route-smoke, opt-in ZAP + VRT |
| `reusable-pantheon-deploy-rc-multidev.yml` | PR merged to develop (real merges only) | `rc-YYYY-WW` multidev, composer-audit gate, route-smoke, ZAP, opt-in VRT |
| `reusable-pantheon-deploy-epic-multidev.yml` | push to `epic/**` | `epr-*` multidev, ZAP gate |
| `reusable-pantheon-vrt.yml` | called by the multidev workflows | Playwright screenshots LIVE vs multidev, diff report to S3, job summary |
| `reusable-pantheon-security-scan.yml` | called by the multidev workflows | OWASP ZAP baseline, reports to S3, job summary |
| `reusable-route-smoke.yml` | called by the multidev workflows | authenticated key-route checks from `.github/smoke-routes.txt` |
| `reusable-php-quality.yml` | called by the PR multidev workflow | plugin class-load check + unit suites |
| `reusable-composer-diff.yml` | PR opened/updated | composer.lock diff as a sticky PR comment |
| `reusable-semantic-release.yml` | called by the DEV deploy | version + changelog from conventional commits |
| `reusable-satis-publish.yml` | module/theme repos | verify a tagged package is published on the Satis registry |

Each file's header comment is the reference for its inputs, gates, labels and skip flags. Per-repo knobs live in the client repo under `.github/workflow_config/` (`vrt-config.yml`, `.pantheon-workflows-manifest.json`) and `.github/smoke-routes.txt`.

## Composite actions (`.github/actions/`)

- `terminus-install` — pinned Terminus release + machine-token login.
- `pantheon-push` — PHP + Composer install, push the workspace to a Pantheon env, verify the ref landed.
- `pantheon-post-deploy-drush` — waits for the env, then `drush deploy` (updb → cr → cim → cr → deploy:hook) and cache clear.

## What a client repo needs

- **One secret:** `OP_SERVICE_ACCOUNT_TOKEN` (org-level). Every other credential is read from the 1Password `s360-cicd` vault at run time; nothing else is stored in GitHub.
- **Three variables:** `PANTHEON_SITE`, `SLACK_CHANNEL`, `WORKFLOW_SKIP_TERMINUS`.
- **The callers,** installed and kept current by `composer require square360/pantheon-github-workflows`.

## PR labels the workflows read

`--run-vrt`, `--run-security` (opt-in scans), `--skip-multidev`, `--docs-only` (skip the build). Any other label is ignored. `approved`, `needs review`, `released` are lifecycle labels for humans.

## Semantic Release Configuration

These workflows use [semantic-release](https://semantic-release.gitbook.io/) to automatically determine version numbers and generate release notes based on commit messages.

### Supported Commit Types

The workflows are configured to include **all** commit types in release notes, organized into sections:

| Commit Type | Section in Release Notes | Triggers Version Bump |
|-------------|-------------------------|----------------------|
| `feat` | Features | Minor (1.x.0) |
| `fix` | Bug Fixes | Patch (1.0.x) |
| `perf` | Performance Improvements | Patch (1.0.x) |
| `revert` | Reverts | Patch (1.0.x) |
| `refactor` | Code Refactoring | Minor (1.x.0) |
| `chore` | Chores | Patch (1.0.x) |
| `docs` | Documentation | No version bump |
| `style` | Styles | No version bump |
| `test` | Tests | No version bump |
| `build` | Build System | No version bump |
| `ci` | Continuous Integration | No version bump |

### Commit Message Format

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Examples:**
- `feat(auth): add JWT authentication`
- `fix(api): resolve null pointer exception in user endpoint`
- `chore(deps): update drupal core to 10.2.0`
- `docs(readme): update deployment instructions`

### Breaking Changes

To trigger a major version bump (x.0.0), add `BREAKING CHANGE:` in the commit footer:

```
feat(api): change user endpoint response format

BREAKING CHANGE: The user endpoint now returns an array instead of an object
```

Or use the `!` notation:

```
feat!: change API response format
```

## Versioning

Releases are cut by semantic-release on every merge to `main`; the `v4` moving major tag follows the newest 4.x release (`major-tag.yml`). Callers reference `@v4`. Pin a full tag (`@v4.10.2`) only when a repo must stay behind deliberately, and record why in the caller.

## Contributing

When updating workflows:
1. Test changes in a development branch
2. Create a pull request for review
3. Tag releases for version management
4. Update documentation as needed

## Support

For questions or issues with these workflows, please create an issue in this repository.