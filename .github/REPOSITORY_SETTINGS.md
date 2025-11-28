# Repository Settings Guide

This document describes recommended settings for the Aegis GitHub repository.

## ✅ Settings Already Configured

The following settings have been configured via GitHub CLI:

- **Description**: "🛡️ Intelligent AI Agent Orchestration using Asana as Control Plane"
- **Homepage**: https://github.com/daveey/aegis
- **Topics**: ai, agents, anthropic, asana, automation, claude, orchestration, postgresql, python
- **Features Enabled**:
  - ✅ Issues
  - ✅ Discussions
  - ✅ Projects
  - ❌ Wiki (disabled - using docs/ instead)

## 🎨 Social Preview

GitHub allows you to set a social preview image that appears when the repository is shared.

**To set this manually:**

1. Go to: https://github.com/daveey/aegis/settings
2. Scroll to "Social preview"
3. Upload an image (recommended size: 1280x640px)
4. Or use a service like [shields.io](https://shields.io) to generate a badge-style image

**Suggested image elements:**
- Aegis shield logo (🛡️)
- Project name: "Aegis"
- Tagline: "AI Agent Orchestration via Asana"
- Tech stack icons: Python, Asana, Claude, PostgreSQL

## 🔧 Additional Settings to Consider

### General Settings

1. **Default Branch**: Already set to `main` ✅
2. **Template Repository**: Not applicable (project-specific)
3. **Allow merge commits**: Enabled ✅
4. **Allow squash merging**: Enabled (recommended for clean history)
5. **Allow rebase merging**: Enabled
6. **Automatically delete head branches**: Recommended to enable

**To configure merge settings:**
```bash
gh repo edit daveey/aegis \
  --delete-branch-on-merge \
  --enable-squash-merge \
  --enable-merge-commit \
  --enable-rebase-merge
```

### Branch Protection

Already configured via repository rulesets ✅
- Required status check: "CI Success"
- Strict status checks enabled

### Collaborators & Teams

For a single-dev repo:
- No additional collaborators needed
- GitHub Actions has default permissions

### Security & Analysis

Already enabled:
- ✅ Secret scanning
- ✅ Secret scanning push protection
- ❌ Dependabot security updates (consider enabling)
- ❌ Dependabot version updates (consider enabling)

**To enable Dependabot:**

1. Go to: https://github.com/daveey/aegis/settings/security_analysis
2. Enable "Dependabot alerts"
3. Enable "Dependabot security updates"
4. Optionally enable "Dependabot version updates"

Or via CLI:
```bash
gh api -X PATCH /repos/daveey/aegis \
  -f security_and_analysis[dependabot_security_updates][status]=enabled
```

### GitHub Actions

Recommended settings:
- ✅ Allow all actions and reusable workflows
- ✅ Require approval for first-time contributors
- ✅ Store workflow artifacts for 90 days
- ✅ Store workflow logs for 90 days

### Discussions

Enabled ✅

**Recommended categories:**
- 💬 General
- 💡 Ideas
- 🙏 Q&A
- 📣 Announcements
- 🎉 Show and tell

### Pages (GitHub Pages)

Not currently needed, but could be used for:
- Documentation site
- Project website
- API documentation

To enable:
1. Go to: https://github.com/daveey/aegis/settings/pages
2. Select source: GitHub Actions or branch
3. Configure custom domain if desired

### Webhooks

Not needed for single-dev repo unless integrating with external services.

### Environments

Consider creating environments for:
- `development` - No restrictions
- `staging` - Optional approval
- `production` - Required approval + secrets

## 🚀 Recommended Next Steps

1. **Enable Dependabot**:
   ```bash
   # Via web UI at settings/security_analysis
   ```

2. **Enable auto-delete branches**:
   ```bash
   gh repo edit daveey/aegis --delete-branch-on-merge
   ```

3. **Configure Discussion categories**:
   ```bash
   # Via web UI at github.com/daveey/aegis/discussions
   ```

4. **Set up social preview image**:
   ```bash
   # Via web UI at settings (Social preview section)
   ```

5. **Consider enabling GitHub Pages** for documentation:
   ```bash
   # Via web UI at settings/pages
   ```

## 📊 Analytics & Insights

GitHub provides several analytics features:

- **Traffic**: View visitor stats and referrers
- **Insights**: View contributor statistics, code frequency
- **Actions**: View workflow run statistics and costs
- **Security**: View security alerts and advisories

Access these at:
- https://github.com/daveey/aegis/graphs/traffic
- https://github.com/daveey/aegis/pulse
- https://github.com/daveey/aegis/security

## 🏷️ Release Management

When ready to create releases:

1. Use semantic versioning (e.g., v0.1.0, v1.0.0)
2. Create releases via GitHub UI or CLI:
   ```bash
   gh release create v0.1.0 --title "v0.1.0 - Alpha Release" --notes "First alpha release"
   ```
3. Attach build artifacts if applicable
4. Use pre-release tag for alpha/beta versions

## 📝 About Section

Already configured ✅
- Description shows on repository page
- Topics help with discoverability
- Homepage links to repository (can be changed to docs site later)

---

**Last Updated**: 2025-11-28

For questions about repository settings, see [GitHub Docs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features).
