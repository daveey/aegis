# Contributing to Aegis

Thank you for your interest in contributing to Aegis! This document provides guidelines and instructions for contributing to the project.

## 🎯 Project Status

Aegis is currently in **Alpha** status and under active development. We welcome contributions, ideas, and feedback!

## 📋 Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Documentation](#documentation)

## Code of Conduct

This project follows a simple code of conduct:

- **Be respectful** and considerate in all interactions
- **Be collaborative** and help others learn
- **Be open-minded** to different approaches and ideas
- **Focus on what's best** for the project and community

## How Can I Contribute?

### 🐛 Reporting Bugs

Found a bug? Please:

1. **Check existing issues** to avoid duplicates
2. **Use the bug report template** when creating a new issue
3. **Provide detailed information**:
   - Steps to reproduce
   - Expected vs actual behavior
   - Environment details (OS, Python version, etc.)
   - Relevant logs (sanitized of sensitive data)

[Create a Bug Report](https://github.com/daveey/aegis/issues/new?template=bug_report.md)

### ✨ Suggesting Features

Have an idea? Please:

1. **Check existing issues and discussions** for similar ideas
2. **Use the feature request template**
3. **Describe the use case** and problem it solves
4. **Consider implementation complexity** and project scope

[Create a Feature Request](https://github.com/daveey/aegis/issues/new?template=feature_request.md)

### 💬 Participating in Discussions

- Ask questions in [GitHub Discussions](https://github.com/daveey/aegis/discussions)
- Share your use cases and experiences
- Help others with their questions
- Discuss design decisions and architectural choices

### 💻 Contributing Code

We welcome code contributions! See [Development Setup](#development-setup) below.

### 📚 Improving Documentation

Documentation improvements are always welcome:

- Fix typos or unclear explanations
- Add examples and use cases
- Improve installation instructions
- Create tutorials or guides

## Development Setup

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 16+
- [uv](https://github.com/astral-sh/uv) for package management
- Git
- Asana API token (for integration tests)
- Anthropic API key (for integration tests)

### Initial Setup

```bash
# Fork and clone the repository
git clone https://github.com/YOUR-USERNAME/aegis.git
cd aegis

# Add upstream remote
git remote add upstream https://github.com/daveey/aegis.git

# Create virtual environment
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install development dependencies
uv pip install -e ".[test,dev]"

# Set up environment
cp .env.example .env
# Edit .env with your credentials

# Set up database
createdb aegis_test
alembic upgrade head

# Run tests to verify setup
pytest tests/unit/ -v
```

### Keeping Your Fork Updated

```bash
# Fetch upstream changes
git fetch upstream

# Merge upstream main into your local main
git checkout main
git merge upstream/main

# Push to your fork
git push origin main
```

## Coding Standards

### Code Style

We follow PEP 8 with some modifications:

- **Line length**: 100 characters (not strict)
- **Formatter**: ruff
- **Linter**: ruff
- **Type hints**: Required for all function signatures
- **Docstrings**: Google style for public methods

### Running Code Quality Checks

```bash
# Linting
ruff check src/ tests/

# Formatting
ruff format src/ tests/

# Type checking (if mypy installed)
mypy src/aegis/
```

### Code Organization

- **Imports**: Organize as standard library, third-party, local
- **Functions**: Use `snake_case`
- **Classes**: Use `PascalCase`
- **Constants**: Use `UPPER_SNAKE_CASE`
- **Private methods**: Use `_leading_underscore`

### Example Code Style

```python
"""Module docstring describing the module."""

# Standard library
import asyncio
from datetime import datetime

# Third-party packages
import structlog
from pydantic import Field

# Local imports
from aegis.asana.client import AsanaClient
from aegis.config import Settings

logger = structlog.get_logger()


class TaskProcessor:
    """Process tasks from Asana.

    This class handles task parsing, validation, and execution
    using configured agents.

    Attributes:
        client: Asana API client instance
        config: Application configuration
    """

    def __init__(self, client: AsanaClient, config: Settings) -> None:
        """Initialize task processor.

        Args:
            client: Asana API client
            config: Application settings
        """
        self.client = client
        self.config = config

    async def process_task(self, task_id: str) -> dict[str, any]:
        """Process a single task.

        Args:
            task_id: Asana task GID

        Returns:
            Dictionary containing execution results

        Raises:
            ValueError: If task_id is invalid
            RuntimeError: If task processing fails
        """
        try:
            task = await self.client.get_task(task_id)
            logger.info("processing_task", task_id=task_id)
            # Implementation
            return {"success": True}
        except Exception as e:
            logger.error("task_processing_failed", task_id=task_id, error=str(e))
            raise
```

## Testing Guidelines

### Test Coverage

- Aim for **90%+ coverage** for new code
- All bug fixes should include regression tests
- All new features should include comprehensive tests

### Writing Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_new_feature.py -v

# Run with coverage
pytest --cov=src/aegis --cov-report=html
```

### Test Structure

```python
"""Test module docstring."""

import pytest
from aegis.module import function_to_test


@pytest.mark.unit
def test_function_basic_case():
    """Test basic functionality."""
    result = function_to_test("input")
    assert result == "expected"


@pytest.mark.unit
def test_function_edge_case():
    """Test edge case handling."""
    with pytest.raises(ValueError):
        function_to_test("")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_async_function():
    """Test async function."""
    result = await async_function_to_test()
    assert result is not None
```

### Test Markers

- `@pytest.mark.unit` - Fast, isolated tests
- `@pytest.mark.integration` - Integration tests
- `@pytest.mark.live` - Tests that call live APIs (cost money)
- `@pytest.mark.slow` - Tests that take >1 second

## Commit Messages

### Format

```
<type>: <subject>

<body>

<footer>
```

### Types

- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `style:` - Code style changes (formatting, etc.)
- `refactor:` - Code refactoring
- `test:` - Adding or updating tests
- `chore:` - Maintenance tasks

### Examples

```
feat: add task prioritization system

Implement multi-factor task prioritization with configurable weights
for due dates, dependencies, user priority, project importance, and age.

Closes #42
```

```
fix: prevent duplicate task execution

Add task locking mechanism to prevent multiple agents from executing
the same task concurrently.

Fixes #56
```

### Best Practices

- Use present tense ("add feature" not "added feature")
- Use imperative mood ("move cursor" not "moves cursor")
- First line should be 50 characters or less
- Reference issues and PRs in the footer

## Pull Request Process

### Before Submitting

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/amazing-feature
   ```

2. **Make your changes** following the coding standards

3. **Write tests** for your changes

4. **Run tests** locally:
   ```bash
   pytest tests/
   ```

5. **Update documentation** as needed

6. **Commit your changes** with clear messages

### Submitting the PR

1. **Push to your fork**:
   ```bash
   git push origin feature/amazing-feature
   ```

2. **Open a Pull Request** on GitHub

3. **Fill out the PR template** completely

4. **Link related issues** using "Closes #123" or "Relates to #456"

5. **Wait for CI checks** to pass

6. **Respond to review comments** promptly

### PR Review Process

- PRs require passing CI checks (lint, tests, coverage)
- Maintainers will review your code and provide feedback
- Address feedback and update your PR
- Once approved, maintainers will merge your PR

### After Merge

- Delete your feature branch
- Update your fork:
  ```bash
  git checkout main
  git pull upstream main
  git push origin main
  ```

## Documentation

### What to Document

- **Public APIs**: All public functions and classes
- **Configuration**: New environment variables or settings
- **CLI Commands**: New commands or options
- **Deployment**: Changes to deployment process
- **Breaking Changes**: Any backwards-incompatible changes

### Where to Document

- **Code**: Docstrings for all public APIs
- **README.md**: High-level overview and quick start
- **CLAUDE.md**: AI assistant development guidelines
- **docs/**: Detailed operator and developer guides
- **design/**: Architecture and design decisions

### Documentation Style

- Use clear, concise language
- Include code examples
- Add diagrams for complex concepts
- Keep documentation up to date with code changes

## Questions?

- **General questions**: [GitHub Discussions](https://github.com/daveey/aegis/discussions)
- **Bug reports**: [Create an issue](https://github.com/daveey/aegis/issues/new?template=bug_report.md)
- **Feature requests**: [Create an issue](https://github.com/daveey/aegis/issues/new?template=feature_request.md)
- **Security issues**: See [SECURITY.md](SECURITY.md)

## Attribution

This contributing guide was inspired by open source projects like Django, pytest, and others.

---

Thank you for contributing to Aegis! 🛡️
