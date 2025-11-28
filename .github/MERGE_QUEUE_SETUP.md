# Merge Queue Setup Guide

This repository is configured with GitHub Actions CI and branch protection rules. To enable the **merge queue** feature, follow these steps:

## What's Already Configured ✅

- **CI Workflow** (`.github/workflows/ci.yml`):
  - Lint checks with ruff
  - Unit tests with coverage reporting
  - Integration tests with PostgreSQL and Redis
  - Summary job `CI Success` that must pass

- **Branch Protection** (via ruleset):
  - Required status check: `CI Success`
  - Strict status checks (branches must be up to date)

- **Main Branch**:
  - Default branch set to `main`
  - All PRs must target `main`

## Enable Merge Queue (Manual Step Required)

GitHub's merge queue feature currently requires manual configuration through the web UI. Follow these steps:

### Option 1: Using Repository Rulesets (Recommended)

1. Go to: https://github.com/daveey/aegis/settings/rules/10548731
2. Click "Edit" on the existing "main branch protection" ruleset
3. Scroll to "Add rule" section
4. Select "Require merge queue"
5. Configure merge queue settings:
   - **Method for merging pull requests**: Merge commit
   - **Minimum number of pull requests to merge**: 1
   - **Maximum time to wait before merging**: 0 minutes
   - **Build concurrency**: 5
   - **Merge concurrency**: 5
   - **Status check timeout**: 60 minutes
6. Click "Save changes"

### Option 2: Using Branch Protection Rules (Legacy)

1. Go to: https://github.com/daveey/aegis/settings/branches
2. Find the rule for `main` branch
3. Click "Edit"
4. Check "Require merge queue"
5. Configure the same settings as above
6. Click "Save changes"

## How Merge Queue Works

Once enabled, the merge queue:

1. **Queues PRs**: When you approve a PR and add it to the queue, GitHub creates a temporary merge commit
2. **Runs Tests**: The CI workflow runs on the temporary merge commit (triggered by `merge_group` event)
3. **Validates**: Only if tests pass on the merged state, the PR is merged to `main`
4. **Prevents Breakage**: This prevents the "works on my branch but breaks main" problem

### Workflow Changes for Merge Queue

The CI workflow (`.github/workflows/ci.yml`) already includes support for merge queue:

```yaml
on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]
  merge_group:  # ← This enables merge queue support
    branches: [main, master]
```

## Testing the Setup

1. Create a test branch:
   ```bash
   git checkout -b test-ci
   echo "# Test" >> README.md
   git add README.md
   git commit -m "Test CI"
   git push -u origin test-ci
   ```

2. Create a PR:
   ```bash
   gh pr create --title "Test CI" --body "Testing CI and merge queue"
   ```

3. Wait for CI to pass

4. If merge queue is enabled:
   - Click "Merge when ready" instead of "Merge pull request"
   - The PR will be added to the merge queue
   - GitHub will create a temporary merge commit and run tests
   - If tests pass, the PR will be automatically merged

## Additional Configuration

### Required Secrets

The CI workflow requires these repository secrets to be configured:

- `ASANA_TEST_TOKEN` - Asana API token for testing
- `ASANA_TEST_WORKSPACE` - Test workspace GID
- `ASANA_TEST_PROJECT` - Test project GID
- `ASANA_TEST_PORTFOLIO` - Test portfolio GID
- `ANTHROPIC_API_KEY` - Claude API key for integration tests

Configure secrets at: https://github.com/daveey/aegis/settings/secrets/actions

### Auto-merge

To enable auto-merge for PRs (recommended with merge queue):

1. Go to: https://github.com/daveey/aegis/settings
2. Scroll to "Pull Requests"
3. Check "Allow auto-merge"
4. Save

## Troubleshooting

### CI Not Running

- Check the Actions tab: https://github.com/daveey/aegis/actions
- Verify workflow file syntax is valid
- Check that required secrets are configured

### Merge Queue Not Available

- Merge queue requires a GitHub Team or Enterprise plan
- For free/personal repos, use required status checks without merge queue
- The CI workflow will still protect `main` by requiring tests to pass on PRs

### Tests Failing

- Check logs in the Actions tab
- Verify all dependencies are installed correctly
- Ensure PostgreSQL and Redis services are healthy
- Check that secrets are configured correctly

## References

- [GitHub Merge Queue Documentation](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue)
- [Repository Rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
