<div align="center">

# 🛡️ Aegis

**Intelligent AI Agent Orchestration using Asana as Control Plane**

[![CI Status](https://github.com/daveey/aegis/actions/workflows/ci.yml/badge.svg)](https://github.com/daveey/aegis/actions)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)]()

[Features](#-features) •
[Quick Start](#-quick-start) •
[Architecture](#-architecture) •
[Documentation](#-documentation) •
[Development](#-development)

</div>

---

## 🎯 What is Aegis?

**Aegis** transforms Asana into a powerful AI agent orchestration platform. Instead of building another chat interface, Aegis leverages Asana's familiar project management UI to coordinate complex, multi-step tasks through specialized AI agents powered by Claude.

> **Think of it as:** Your personal AI swarm that lives in Asana, capable of autonomously tackling software development, research, content creation, and more—all managed through tasks you already know how to create.

### Why Asana?

- ✅ **Familiar Interface**: No new tools to learn
- ✅ **Rich Context**: Tasks, subtasks, dependencies, attachments, comments
- ✅ **Natural Workflow**: Integrates with your existing project management
- ✅ **Mobile Access**: Manage AI agents from anywhere
- ✅ **Team Collaboration**: Share context and results effortlessly

---

## ✨ Features

### Currently Available

| Feature | Description |
|---------|-------------|
| 🤖 **Autonomous Execution** | `aegis work-on` processes multiple tasks automatically |
| 🎛️ **Continuous Orchestration** | `aegis start` runs with live task queue and prioritization |
| 📊 **Real-Time Dashboard** | Web interface showing agent status and logs at `http://localhost:8000` |
| 🎯 **Smart Prioritization** | Multi-factor scoring: due dates, dependencies, priority, project, age |
| 💾 **Database Sync** | PostgreSQL storage for projects, tasks, execution history |
| 🔄 **Graceful Shutdown** | Proper signal handling and subprocess management |
| 📝 **Task Execution Logging** | Complete audit trail with token usage and cost tracking |
| 🎨 **Rich Formatting** | Beautiful Asana comments with markdown, code blocks, headers |

### Coming Soon

- 🧠 **Multi-Agent Swarm**: Router, planner, executor, reviewer agents working together
- 🗂️ **Intelligent Decomposition**: Automatic task breakdown with dependency management
- 🔍 **Vector Memory**: Context-aware responses using knowledge base
- 🖼️ **Multi-Modal Support**: Enhanced handling of images and documents

---

## 🏗️ Architecture

<div align="center">

```
┌─────────────────────────────────────────────────────────┐
│                       ASANA                             │
│  (Projects, Tasks, Comments, Sections, Dependencies)   │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│                   AEGIS ORCHESTRATOR                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Task Queue   │  │ Prioritizer  │  │ Agent Pool   │ │
│  │ (Priority)   │→ │ (Multi-      │→ │ (Concurrent  │ │
│  │              │  │  Factor)     │  │  Execution)  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              CLAUDE CODE / API AGENTS                   │
│  - Execute tasks with full AI capabilities              │
│  - Read/write files, run commands, access codebase      │
│  - Return results via stdout/API                        │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              POSTGRESQL DATABASE                        │
│  - Task execution history & token tracking              │
│  - System state & orchestrator status                   │
│  - Projects & tasks cache                               │
└─────────────────────────────────────────────────────────┘
```

</div>

> **📖 Deep Dive**: Read the [complete architecture design](design/PROJECT_OVERVIEW.md) for system components, agent framework, and development phases.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 16+
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- Asana account with API access
- Anthropic API key (Claude)

### Installation

```bash
# Clone the repository
git clone https://github.com/daveey/aegis.git
cd aegis

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your API keys and configuration

# Setup database
createdb aegis
alembic upgrade head

# Verify setup
aegis config
aegis test-asana
```

### Basic Usage

```bash
# Execute a specific task
aegis do "Aegis Project" <task-gid>

# Process all ready tasks in a project (autonomous mode)
aegis work-on "Aegis Project" --max-tasks 5

# Start continuous orchestrator with live dashboard
aegis start "Aegis Project"
# Dashboard available at http://localhost:8000

# Organize project with standard sections
aegis organize "Aegis Project"

# Sync Asana data to local database
aegis sync
```

### Your First Task

1. **Create a task in Asana** in your designated project:
   ```
   Title: "Add logging to database queries"
   Description: Review the database session code and add structured
   logging for all queries to help with debugging.
   ```

2. **Run Aegis**:
   ```bash
   aegis do "Aegis Project"
   ```

3. **Check Asana** for the result posted as a comment!

---

## 📚 Documentation

### For Operators

- **[Operator Guide](docs/OPERATOR_GUIDE.md)** - Complete installation and operations guide
- **[CLI Reference](TOOLS.md)** - All commands and options
- **[Shutdown Handling](docs/SHUTDOWN_HANDLING.md)** - Signal handling and graceful termination
- **[Task Prioritization](docs/PRIORITIZATION.md)** - How tasks are scored and ordered

### For Developers

- **[Project Overview](design/PROJECT_OVERVIEW.md)** - Vision, architecture, system design
- **[Task List & Roadmap](design/TASK_LIST.md)** - Development phases and implementation plan
- **[Database Schema](design/DATABASE_SCHEMA.md)** - Data models and relationships
- **[Orchestration Design](design/ORCHESTRATION.md)** - Orchestrator architecture
- **[Project Structure](PROJECT_STRUCTURE.md)** - Complete file-by-file documentation (18,666 lines mapped)
- **[Claude Guide](CLAUDE.md)** - AI assistant development guidelines

### Testing

- **[E2E Test Guide](tests/integration/E2E_TEST_GUIDE.md)** - Integration testing
- **[Test Summary](tests/integration/TEST_SUMMARY.md)** - Test coverage overview

---

## 🎨 Project Structure

```
aegis/
├── .github/                    # GitHub Actions workflows
│   ├── workflows/ci.yml        # CI pipeline with merge queue support
│   └── MERGE_QUEUE_SETUP.md    # Merge queue configuration guide
├── src/aegis/                  # Source code
│   ├── asana/                  # Asana API client (530 lines)
│   ├── agents/                 # Agent implementations
│   ├── orchestrator/           # Orchestration engine (983 lines)
│   ├── database/               # PostgreSQL models & CRUD
│   ├── sync/                   # Asana sync functionality
│   ├── utils/                  # Utilities (shutdown, helpers)
│   ├── cli.py                  # CLI interface (950 lines)
│   └── config.py               # Configuration management
├── tests/                      # Test suite
│   ├── unit/                   # 36 tests, 92% coverage
│   └── integration/            # 14 E2E tests
├── design/                     # Design documents
├── docs/                       # Operator documentation
├── prompts/                    # Agent prompt templates
└── examples/                   # Usage examples
```

> **📖 Complete Map**: See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for detailed file-by-file documentation

---

## 🛠️ Development

### Setting Up Development Environment

```bash
# Install with development dependencies
uv pip install -e ".[test,dev]"

# Install pre-commit hooks (if configured)
pre-commit install

# Run tests
pytest tests/unit/ -v

# Run integration tests (requires credentials)
pytest tests/integration/ -v

# Check coverage
pytest --cov=src/aegis --cov-report=html
```

### Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Specific test file
pytest tests/unit/test_prioritizer.py -v

# With coverage
pytest --cov=src/aegis --cov-report=term-missing
```

### Code Quality

```bash
# Linting
ruff check src/ tests/

# Formatting
ruff format src/ tests/

# Type checking (if mypy installed)
mypy src/aegis/
```

---

## 🤝 Contributing

This is currently a personal project in early development. Contributions, ideas, and feedback are welcome!

### How to Contribute

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes**: Follow the code style and add tests
4. **Run tests**: `pytest tests/`
5. **Commit your changes**: `git commit -m "Add amazing feature"`
6. **Push to the branch**: `git push origin feature/amazing-feature`
7. **Open a Pull Request**

### Development Guidelines

- All code must pass CI checks (lint, tests, type checking)
- Add tests for new features
- Update documentation as needed
- Follow existing code patterns
- Use structured logging with `structlog`
- Keep commits atomic and well-described

See [CLAUDE.md](CLAUDE.md) for detailed development guidelines.

---

## 📊 Project Status

**Current Phase:** Alpha (MVP Complete)

- ✅ **Phase 1 (Foundation)**: Basic Asana integration + single agent execution
- 🚧 **Phase 2 (Orchestration)**: Multi-agent coordination and task decomposition
- 📋 **Phase 3 (Intelligence)**: Advanced memory, learning, context retrieval
- 📋 **Phase 4 (Scale)**: Production infrastructure and multi-tenancy

### Recent Updates

- ✅ Autonomous `aegis work-on` command for batch execution
- ✅ Continuous orchestrator with live dashboard
- ✅ Multi-factor task prioritization system
- ✅ Graceful shutdown handling with signal management
- ✅ SimpleExecutor agent with Claude API integration
- ✅ Database sync for projects and tasks
- ✅ CI/CD pipeline with branch protection

---

## 🔒 Security

Found a security issue? Please email security concerns to the maintainer instead of opening a public issue.

See [SECURITY.md](SECURITY.md) for our security policy.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **[Claude](https://www.anthropic.com/claude)** - The AI powering agent execution
- **[Asana](https://asana.com)** - The project management platform
- **[Claude Code](https://code.anthropic.com)** - Development tool integration
- **Community** - For inspiration and ideas

---

## 📞 Contact & Support

- **Issues**: [GitHub Issues](https://github.com/daveey/aegis/issues)
- **Discussions**: [GitHub Discussions](https://github.com/daveey/aegis/discussions)
- **Maintainer**: [@daveey](https://github.com/daveey)

---

<div align="center">

**Built with ❤️ using Claude Code**

[⬆ Back to Top](#-aegis)

</div>
