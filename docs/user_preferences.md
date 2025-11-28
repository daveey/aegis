# User Preferences

> **Purpose**: This file stores accumulated user rules, style guides, and preferences.
> Updated by the Documentation Agent when users provide "Preference:" tasks.

## Code Style

### Python
- Use `uv` for package management
- Imports go at top of file
- Type hints for all function signatures
- Google-style docstrings
- structlog for logging
- Pydantic for data validation

### Git
- Never force push to main/master
- Always run tests before merging
- Use conventional commit messages
- Create feature branches with descriptive names

## Project Conventions

### File Organization
- Source code: `src/aegis/`
- Tests: `tests/unit/` and `tests/integration/`
- Documentation: `docs/`
- Scripts: `scripts/` or `tools/`

### Testing
- Unit tests for all infrastructure components
- Integration tests for API interactions
- E2E tests for critical workflows
- Aim for 90%+ test coverage

### Error Handling
- Use structured logging with context
- Custom exceptions for domain errors
- Always clean up resources (use context managers)
- Log errors before re-raising

## Communication Preferences

### Asana Comments
- Keep summaries under 50 words
- Use emojis for visual status
- Link to detailed logs in dashboard
- Format according to template in design.md

### Code Comments
- Only add comments where logic isn't self-evident
- Prefer self-documenting code names
- Document "why" not "what"

## Deployment Preferences

### Safety
- Always use PID locking for orchestrator
- Enforce cost limits on agent execution
- Never skip tests in CI/CD
- Manual approval for production deployments

---

**Last Updated**: 2025-11-28
