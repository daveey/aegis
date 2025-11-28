# Fix Documentation

This directory contains documentation for specific bug fixes and issue resolutions.

## Purpose

These documents:
- **Describe the problem**: What was broken or not working
- **Explain the root cause**: Why the issue occurred
- **Detail the solution**: How it was fixed
- **Prevent regressions**: Help avoid similar issues in the future

## Organization

Files use the naming pattern: `ISSUE_DESCRIPTION_FIX.md`

## Documents

- `AGENT_SERVICE_STARTUP_FIX.md` - Agent service startup issues
- `DUPLICATE_QUESTIONS_FIX.md` - Duplicate question creation bug
- `ORCHESTRATOR_DISPLAY_FIX.md` - Orchestrator display issues

## Guidelines

When documenting a fix:
1. **Problem statement**: Clear description of the issue
2. **Reproduction steps**: How to trigger the bug
3. **Root cause analysis**: Why it happened
4. **Solution**: What was changed
5. **Testing**: How to verify the fix
6. **Related issues**: Link to GitHub issues if applicable

### Template

```markdown
# [Issue Name] Fix

## Problem

Description of what was broken.

## Root Cause

Explanation of why it occurred.

## Solution

What was changed to fix it.

## Testing

How to verify the fix works.

## Related

- Issue #123
- Commit abc123
```

---

**Note**: For ongoing troubleshooting, see the operator guide at [`docs/OPERATOR_GUIDE.md`](../OPERATOR_GUIDE.md).
