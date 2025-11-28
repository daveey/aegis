# Aegis

**Intelligent Assistant Orchestration System using Asana as the Control Plane**

Aegis is an autonomous agent swarm orchestration platform that uses Asana for task management and communication. Instead of building yet another chat interface, Aegis leverages Asana's familiar project management UI to coordinate complex, multi-step tasks through specialized AI agents.

## Quick Start

### For Operators

To install and run Aegis:

1. Review the [Operator Guide](docs/OPERATOR_GUIDE.md) for complete setup instructions
2. Install dependencies: `uv pip install -e .`
3. Configure environment: Copy `.env.example` to `.env` and fill in credentials
4. Setup database: `alembic upgrade head` (creates PostgreSQL tables)
5. Test connection: `aegis test-asana`
6. Execute tasks: `aegis do <project_name>` or start orchestrator: `aegis start <project_name>`

### For Developers

To contribute to Aegis development:

1. Review the project vision and architecture in [`design/PROJECT_OVERVIEW.md`](design/PROJECT_OVERVIEW.md)
2. Check the detailed task list and roadmap in [`design/TASK_LIST.md`](design/TASK_LIST.md)
3. **Read [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) for complete file-by-file documentation** (18,666 lines mapped)
4. Review [`CLAUDE.md`](CLAUDE.md) for AI assistant development guidelines
5. Start with Phase 1 (Foundation/MVP) tasks

## Project Structure

> 📚 **For detailed file-by-file documentation**, see [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)

```
aegis/
├── design/                      # Design documents and planning
│   ├── PROJECT_OVERVIEW.md      # High-level project description
│   ├── TASK_LIST.md             # Detailed task breakdown and roadmap
│   ├── DATABASE_SCHEMA.md       # Database design
│   └── ORCHESTRATION.md         # Orchestration architecture
├── docs/                        # Operator documentation
│   ├── OPERATOR_GUIDE.md        # Installation and operations guide
│   ├── SHUTDOWN_HANDLING.md     # Shutdown implementation docs
│   └── PRIORITIZATION.md        # Task prioritization docs
├── src/aegis/                   # Source code
│   ├── asana/                   # Asana API client
│   │   ├── client.py            # AsanaClient wrapper (530 lines)
│   │   └── models.py            # Pydantic models for Asana entities
│   ├── agents/                  # Agent implementations
│   │   ├── simple_executor.py   # SimpleExecutor agent (398 lines)
│   │   ├── formatters.py        # Response formatters
│   │   └── prompts.py           # Prompt templates
│   ├── database/                # Database models and operations
│   │   ├── models.py            # SQLAlchemy ORM models (348 lines)
│   │   ├── crud.py              # CRUD operations (989 lines)
│   │   ├── session.py           # Database session management
│   │   └── state.py             # System state tracking
│   ├── orchestrator/            # Orchestration logic
│   │   ├── main.py              # Main orchestrator (983 lines)
│   │   ├── web.py               # Web dashboard (590 lines)
│   │   ├── prioritizer.py       # Task prioritization (387 lines)
│   │   └── display.py           # Rich console display
│   ├── sync/                    # Asana sync functionality
│   │   └── asana_sync.py        # Sync projects and tasks (294 lines)
│   ├── utils/                   # Utilities
│   │   └── shutdown.py          # Graceful shutdown handler (376 lines)
│   ├── config.py                # Configuration management (130 lines)
│   ├── cli.py                   # Command-line interface (950 lines)
│   └── agent_helpers.py         # Helper functions for agents
├── tests/                       # Test suite
│   ├── unit/                    # Unit tests
│   │   ├── test_prioritizer.py  # 36 tests, 92% coverage
│   │   ├── test_shutdown.py     # 29 tests, 91% coverage
│   │   └── test_formatters.py   # Response formatter tests
│   └── integration/             # Integration tests
│       ├── test_e2e.py          # 14 E2E tests
│       └── E2E_TEST_GUIDE.md    # Complete testing guide
├── alembic/                     # Database migrations
│   └── versions/                # Migration scripts
├── logs/                        # Execution logs
│   ├── aegis.log                # Main log file
│   └── agents/                  # Per-task agent logs
├── CLAUDE.md                    # AI assistant development guide
└── README.md                    # This file
```

## Core Concept

Users interact with Aegis through Asana by:
- Creating tasks in designated Asana projects
- Assigning tasks to Aegis
- Providing requirements in task descriptions
- Receiving updates through comments and status changes
- Getting deliverables via attachments

Aegis orchestrates a swarm of specialized agents to:
- Parse and understand task requirements
- Decompose complex tasks into subtasks
- Execute work using Claude Code and other tools
- Coordinate multiple agents working in parallel
- Report progress and ask clarifying questions
- Deliver results back through Asana

## Key Features

**✅ Implemented**:
- **Asana-First Interface**: All interaction through Asana projects and tasks
- **Autonomous Execution**: `aegis work-on` processes multiple tasks automatically
- **Continuous Monitoring**: `aegis start` runs orchestrator with task queue and prioritization
- **Real-Time Dashboard**: Web interface showing live agent status and logs
- **Task Prioritization**: Multi-factor scoring (due date, dependencies, user priority, project, age)
- **SimpleExecutor Agent**: Claude API-based task execution with database logging
- **Database Sync**: PostgreSQL storage for projects, tasks, and execution history
- **Graceful Shutdown**: Proper signal handling and subprocess management

**🚧 In Progress**:
- **Agent Mentions**: `aegis process-agent-mentions` for @-mention based interactions
- **Task Planning**: `aegis plan` for backlog organization

**📋 Planned**:
- **Multi-Agent Swarm**: Router, planner, executor, reviewer agents
- **Intelligent Decomposition**: Automatic task breakdown and dependency management
- **Knowledge Management**: Vector database for context and memory
- **Multi-Modal Support**: Enhanced handling of images and documents

## Development Phases

1. **Phase 1 - Foundation (MVP)**: Basic Asana integration + single agent execution
2. **Phase 2 - Orchestration**: Multi-agent coordination and task decomposition
3. **Phase 3 - Intelligence**: Advanced memory, learning, and context retrieval
4. **Phase 4 - Scale**: Production infrastructure and multi-tenancy

## Tech Stack

- **Language**: Python 3.11+
- **LLM**: Claude (Anthropic API / Claude Code)
- **Interface**: Asana API
- **Database**: PostgreSQL + Vector DB (Pinecone/Qdrant)
- **Cache**: Redis
- **Orchestration**: asyncio-based custom framework

## Current Status

🏗️ **Alpha** - Basic functionality implemented, active development ongoing

## Documentation

### For Operators
- [Operator Guide](docs/OPERATOR_GUIDE.md) - Complete installation, configuration, and operations guide
- [Tools Reference](TOOLS.md) - CLI commands and usage

### For Developers
- [Project Overview](design/PROJECT_OVERVIEW.md) - Vision, architecture, and system design
- [Task List](design/TASK_LIST.md) - Detailed implementation roadmap
- [Database Schema](design/DATABASE_SCHEMA.md) - Database design and models

## Contributing

This is currently a personal project in early design stages. More information on contributing will be added as the project develops.

## License

TBD
