# GitHub Copilot Instructions for Square360 Shared Pantheon Workflows

This file contains specific instructions for GitHub Copilot when working with this repository's GitHub Actions workflows and Pantheon deployment automation.

## Repository Context

This repository contains reusable GitHub Actions workflows for deploying Drupal sites to Pantheon hosting platform. The main workflows are:

- `reusable-deploy-pantheon.yml` - Deploys to Pantheon environments with semantic release
- `reusable-deploy-multidev.yml` - Deploys PRs to Pantheon multidev environments
- `reusable-semantic-release.yml` - Handles semantic versioning and releases

## Key Technologies & Dependencies

- **GitHub Actions**: Workflow automation platform
- **Pantheon**: Drupal hosting platform with Terminus CLI
- **pantheon-systems/push-to-pantheon@0.7.0**: Primary action for Pantheon deployments
- **Semantic Release**: Automated versioning and changelog generation
- **Terminus**: Pantheon's command-line interface
- **Drush**: Drupal command-line tool

## Workflow Patterns & Conventions

### 1. Reusable Workflow Structure
All workflows follow this pattern:
```yaml
name: Reusable [Workflow Name]
on:
  workflow_call:
    inputs:
      # Required and optional inputs
    secrets:
      # Required secrets
```

### 2. Required Secrets Pattern
Standard secrets across all workflows:
- `PANTHEON_SSH_KEY`: SSH key for Pantheon Git access
- `PANTHEON_MACHINE_TOKEN`: Pantheon API authentication
- Semantic release pushes with a short-lived token from the "Square360 CI" GitHub App (`s360-cicd/github-app-ci` in 1Password), not a personal token

### 3. Input Parameter Conventions
- Use descriptive names with underscores
- Always include `description`, `required`, and `type`
- Provide sensible defaults for optional inputs
- `pantheon_site`: Always required string input
- `slack_channel`: Optional string for Slack notifications (e.g., `#deployments`)
- `slack_webhook_url`: Optional string for Slack webhook URL (organization variable)

### 4. Environment Variable Patterns
- Use `TERMINUS_MACHINE_TOKEN` for Terminus CLI authentication
- Set shell to `bash` in defaults
- Use `-n` flag for non-interactive Terminus commands

## Pantheon-Specific Guidelines

### 1. pantheon-systems/push-to-pantheon Action
When referencing this action:
- **Always use exact version pinning** (e.g., `@0.7.0`) - This is Pantheon's official recommendation
- Current stable version: `@0.7.0` (as of October 2025)
- **Why exact versioning?**
  - Action is in "Early Access" (pre-1.0.0) and may have breaking changes
  - Pantheon explicitly recommends pinning to prevent unexpected behavior changes
  - Input parameter names and behaviors may change between versions
  - No major version tags (like `@v0`) are available yet
- **When to update:**
  - Check for new releases periodically
  - Test thoroughly in development before updating production
  - Once 1.0.0 is released, consider switching to major version pinning (`@v1`)
- Required parameters: `ssh_key`, `machine_token`, `site`, `target_env`
- Standard settings:
  ```yaml
  git_user_name: ${{ github.event.pull_request.user.login || github.actor }}
  git_user_email: ${{ github.event.pull_request.user.email || format('{0}@users.noreply.github.com', github.actor) }}
  delete_old_environments: false
  clone_content: false
  ```

### 2. Terminus Command Patterns
Standard Drupal deployment commands:
```bash
terminus -n drush ${{ inputs.pantheon_site }}.${{ inputs.target_env }} -- updb -y    # Database updates
terminus -n drush ${{ inputs.pantheon_site }}.${{ inputs.target_env }} -- cim -y     # Config import
terminus -n drush ${{ inputs.pantheon_site }}.${{ inputs.target_env }} -- cr -y      # Cache rebuild
```

### 3. Backup Management
- Check backup age before creating new ones
- Use `--keep-for=30` for backup retention
- Create backups on `live` environment before deployments

## Semantic Release Integration

### 1. Configuration Pattern
Create semantic-release config dynamically if not present:
```yaml
- name: Create semantic-release configuration
  run: |
    cat > package.json << 'EOF'
    {
      "name": "semantic-release-config",
      "private": true,
      "release": {
        "branches": ["master", "main"],
        "plugins": [
          "@semantic-release/commit-analyzer",
          "@semantic-release/release-notes-generator",
          "@semantic-release/changelog",
          "@semantic-release/github",
          [
            "@semantic-release/git",
            {
              "assets": ["CHANGELOG.md"],
              "message": "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}"
            }
          ]
        ]
      }
    }
    EOF
```

### 2. Branch Context Handling
Force semantic-release to run in push context for PR-triggered workflows:
```bash
export GITHUB_EVENT_NAME=push
export GITHUB_REF=refs/heads/${{ github.event.pull_request.base.ref || github.ref_name }}
export GITHUB_HEAD_REF=""
export GITHUB_BASE_REF=""
```

## Slack Notifications

### 1. Configuration
Slack notifications are optional and configured via inputs:
- `slack_channel`: Channel name for notifications (e.g., `#deployments`)
- `slack_webhook_url`: Organization variable containing webhook URL

### 2. Notification Content
Notifications include:
- Deployment status (success/failure/cancelled)
- Repository and environment information
- Pantheon site details
- Environment URL (on success)
- Workflow link for troubleshooting
- Pull request link (for multidev deployments)

### 3. Usage Pattern
```yaml
jobs:
  deploy:
    uses: Square360/shared-pantheon-workflows/.github/workflows/reusable-deploy-pantheon.yml@main
    with:
      pantheon_site: ${{ vars.PANTHEON_SITE }}
      slack_channel: ${{ vars.SLACK_CHANNEL }}
      slack_webhook_url: ${{ vars.SLACK_WEBHOOK_URL }}
```

## Code Quality Standards

### 1. YAML Formatting
- Use 2-space indentation
- Always quote string values that could be interpreted as other types
- Use `|` for multi-line strings in run commands
- Group related steps with descriptive names

### 2. Job Dependencies
- Use `needs` for job dependencies
- Use `if: ${{ always() && (needs.job.result == 'success' || needs.job.result == 'skipped') }}` for conditional execution
- Handle both success and skipped states appropriately

### 3. Error Handling
- Use `-y` flags for non-interactive commands
- Include `--no-interaction` and `--quiet` for Terminus commands
- Provide meaningful step names and commit messages

## Security Considerations

### 1. Secret Handling
- Never log or echo secrets
- Use `env:` blocks for secret assignment to commands
- Mark optional secrets appropriately in workflow_call

### 2. Permissions
Set minimal required permissions:
```yaml
permissions:
  deployments: write
  contents: write
  pull-requests: read  # or write for multidev workflows
```

### 3. Checkout Behavior
- Use `fetch-depth: 1` for shallow clones when possible
- Use `ref: ${{ github.event.pull_request.base.ref || github.ref }}` for target branch checkout
- Disable `persist-credentials: false` for semantic release security

## Testing & Debugging

### 1. Workflow Testing
- Test in development branches before merging
- Use `--debug` flag for semantic-release troubleshooting
- Validate YAML syntax before committing

### 2. Common Issues
- Multidev environment naming: use sanitized PR numbers or branch names
- Git user configuration: always set before semantic-release
- Backup timing: check `backup_hours_threshold` logic carefully

## Maintenance Guidelines

### 1. Version Updates
- Pin action versions (e.g., `@0.7.0`) for stability
- Test action updates in development before production
- Update documentation when changing versions

### 2. Workflow Versioning
- Tag releases for workflow versions
- Use semantic versioning for workflow releases
- Maintain backward compatibility when possible

### 3. Documentation
- Update README.md when adding new workflows
- Include usage examples for all new inputs
- Document breaking changes in CHANGELOG.md

## Common Patterns for New Workflows

When creating new workflows, follow this template:
```yaml
name: Reusable [Descriptive Name]

on:
  workflow_call:
    inputs:
      pantheon_site:
        description: 'Pantheon site name'
        required: true
        type: string
      # Additional inputs...
    secrets:
      PANTHEON_SSH_KEY:
        required: true
      PANTHEON_MACHINE_TOKEN:
        required: true

defaults:
  run:
    shell: bash

jobs:
  job_name:
    name: [Descriptive Job Name]
    runs-on: ubuntu-latest
    permissions:
      # Minimal required permissions
    steps:
      - uses: actions/checkout@v4
      # Additional steps...
```

Remember: These workflows are shared across multiple projects, so changes should be backward-compatible and well-tested.