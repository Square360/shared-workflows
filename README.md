# Square360 Shared Pantheon Workflows

This repository contains reusable GitHub Actions workflows for Square360 Pantheon projects.

## Available Workflows

### Pantheon Deployment Workflows

#### `reusable-deploy-pantheon.yml`
Deploys code to Pantheon environments with optional semantic release.

**Usage:**
```yaml
jobs:
  deploy:
    uses: Square360/shared-pantheon-workflows/.github/workflows/reusable-deploy-pantheon.yml@main
    with:
      pantheon_site: ${{ vars.PANTHEON_SITE }}
      target_env: "dev"
      backup_hours_threshold: 6
      run_semantic_release: true
    secrets:
      PANTHEON_SSH_KEY: ${{ secrets.PANTHEON_SSH_KEY }}
      PANTHEON_MACHINE_TOKEN: ${{ secrets.PANTHEON_MACHINE_TOKEN }}
      CI_GH_TOKEN: ${{ secrets.CI_GH_TOKEN }}
```

**Inputs:**
- `pantheon_site` (required): Pantheon site name
- `target_env` (optional): Target environment (default: "dev")
- `backup_hours_threshold` (optional): Hours threshold for backup check (default: 6)
- `run_semantic_release` (optional): Whether to run semantic release first (default: true)

#### `reusable-deploy-multidev.yml`
Deploys pull requests to Pantheon multidev environments.

**Usage:**
```yaml
jobs:
  deploy:
    uses: Square360/shared-pantheon-workflows/.github/workflows/reusable-deploy-multidev.yml@main
    with:
      pantheon_site: ${{ vars.PANTHEON_SITE }}
      pr_number: ${{ github.event.pull_request.number }}
      base_ref: ${{ github.base_ref }}
      action: ${{ github.event.action }}
    secrets:
      PANTHEON_SSH_KEY: ${{ secrets.PANTHEON_SSH_KEY }}
      PANTHEON_MACHINE_TOKEN: ${{ secrets.PANTHEON_MACHINE_TOKEN }}
```

### Visual Regression Testing

#### `reusable-visual-regression.yml`
Runs Playwright-based visual regression between the live Pantheon environment and a release-candidate multidev, uploads the report to S3, and (optionally) posts results to the PR, ClickUp, and Slack. Emits both an `index.html` report and a spec-compliant `report.json` for AI consumers (`schema_version: "1.0"`).

**Usage:**
```yaml
jobs:
  vrt:
    uses: Square360/shared-pantheon-workflows/.github/workflows/reusable-visual-regression.yml@main
    with:
      pantheon_site: ${{ vars.PANTHEON_SITE }}
      target_env: ${{ github.event.pull_request.number && format('pr-{0}', github.event.pull_request.number) || 'dev' }}
      slack_channel: "#vrt-alerts"
    secrets:
      PANTHEON_MACHINE_TOKEN: ${{ secrets.PANTHEON_MACHINE_TOKEN }}
      AWS_ACCESS_KEY_ID:     ${{ secrets.AWS_ACCESS_KEY_ID }}
      AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
      AWS_S3_BUCKET:         ${{ secrets.AWS_S3_BUCKET }}
      AWS_S3_REGION:         ${{ secrets.AWS_S3_REGION }}
      CLICKUP_API_TOKEN:     ${{ secrets.CLICKUP_API_TOKEN }}
      CLICKUP_TEAM_ID:       ${{ secrets.CLICKUP_TEAM_ID }}
      SLACK_BOT_TOKEN:       ${{ secrets.SLACK_BOT_TOKEN }}
```

**Inputs:**
- `pantheon_site` (required): Pantheon site machine name
- `target_env` (required): Candidate environment (e.g. `pr-42`, `rc-2026-16`)
- `slack_channel` (optional): Slack channel for notifications
- `force_run` (optional): Skip the `[vrt]` PR-body tag check and run unconditionally (for manual triggers)
- `pr_head_ref` (optional): PR head branch name — used for ClickUp ID fallback on manual runs

**Trigger model:** The workflow only runs when the PR body contains a `[vrt]` tag, optionally with a ClickUp task ID: `[vrt YMAC-959]`. An optional `[vrt-pages]...[/vrt-pages]` block adds extra paths on top of those in `.github/workflow_config/vrt-config.yml`.

#### Prerequisites: S3 bucket and bucket policy

The VRT workflow uploads the report and screenshots to an S3 bucket (we use `square360-vrt-reports`). The bucket policy must grant public read to five path patterns — miss any one of them and either the HTML report won't render or the AI-consumable JSON will contain broken image links.

The JSON's `images.baseline_url` and `images.candidate_url` fields reference absolute URLs under `live/*` and `rc/*`. Those prefixes must be publicly readable for the JSON to be fully consumable — the HTML report inlines screenshots as base64, so it masks gaps in the policy, but the JSON does not.

**Bucket policy (minimum):**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicReadReportsAndImages",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": [
        "arn:aws:s3:::<your-bucket>/*/report.html",
        "arn:aws:s3:::<your-bucket>/*/report.json",
        "arn:aws:s3:::<your-bucket>/*/diff/*",
        "arn:aws:s3:::<your-bucket>/*/live/*",
        "arn:aws:s3:::<your-bucket>/*/rc/*"
      ]
    }
  ]
}
```

**Safety note:** This grants public read to every VRT baseline and candidate screenshot the bucket will ever store. That's fine for anonymous-user pages (marketing pages, public content) but re-evaluate if VRT ever runs against authenticated areas of a site — those screenshots would also become publicly readable under this policy.

**Block Public Access:** The bucket's Block Public Access settings must allow policies that grant public access. If saving the policy fails, that's usually why.

**IAM user for the workflow:** The `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` pair needs `s3:PutObject` on the bucket. Keep that separate from the public-read policy above — the IAM user writes, everyone reads.

## Setup Instructions

### 1. Repository Setup

1. Create a new repository named `shared-pantheon-workflows` in your organization
2. Copy the workflow files from this repository to `.github/workflows/`
3. Update your project repositories to use these shared workflows

### 2. Required Secrets
Each project using these workflows needs these secrets configured:

**For deploy workflows:**
- `PANTHEON_SSH_KEY`: SSH key for Pantheon access
- `PANTHEON_MACHINE_TOKEN`: Pantheon machine token
- `CI_GH_TOKEN`: GitHub token for semantic release (optional)

**For the VRT workflow (in addition to `PANTHEON_MACHINE_TOKEN`):**
- `AWS_ACCESS_KEY_ID`: IAM access key with `s3:PutObject` on the VRT bucket
- `AWS_SECRET_ACCESS_KEY`: Matching secret for the IAM key
- `AWS_S3_BUCKET`: Bucket name (e.g. `square360-vrt-reports`)
- `AWS_S3_REGION`: Bucket region (optional; defaults to `us-east-1`)
- `CLICKUP_API_TOKEN`: ClickUp personal token for posting VRT results to tasks (optional)
- `CLICKUP_TEAM_ID`: ClickUp team ID (optional)
- `SLACK_BOT_TOKEN`: Slack bot token for VRT notifications (optional)

### 3. Required Variables
- `PANTHEON_SITE`: Your Pantheon site name

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

We recommend pinning to specific versions for production use:
```yaml
uses: Square360/shared-pantheon-workflows/.github/workflows/reusable-deploy-pantheon.yml@v1.0.0
```

For development, you can use the latest version:
```yaml
uses: Square360/shared-pantheon-workflows/.github/workflows/reusable-deploy-pantheon.yml@main
```

## Contributing

When updating workflows:
1. Test changes in a development branch
2. Create a pull request for review
3. Tag releases for version management
4. Update documentation as needed

## Support

For questions or issues with these workflows, please create an issue in this repository.