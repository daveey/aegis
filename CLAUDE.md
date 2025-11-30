# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Development
- **Install Dependencies**: `uv sync`
- **Run Tests**: `pytest` (all) or `pytest tests/unit` (unit only)
- **Run Single Test**: `pytest tests/path/to/test.py::test_name`
- **Type Check**: `pyright`
- **Format/Lint**: `ruff check .`

### Orchestrator Operations
- **Start Master Process**: `aegis start` (launches orchestrator + dashboard)
- **Start Without Dashboard**: `aegis start --no-dashboard`
- **Stop Orchestrator**: `aegis stop`
- **Check Status**: `aegis status`
- **Track Project**: `aegis track <PROJECT_NAME_OR_GID>`

### Asana Synchronization
- **Sync Project Schema**: `python tools/sync_asana_project.py --project <GID>`
  - Ensures Asana project has correct sections and custom fields

## Architecture Overview

Aegis is an **Asana-driven agent swarm** for autonomous software development:

- **State Store**: Asana is the single source of truth (tasks, status, assignments)
- **Master Process** (`src/aegis/orchestrator/master.py`): Manages agent lifecycle and work queue
- **Syncer Agents** (`src/aegis/agents/syncer.py`): Poll Asana projects, populate work queue
- **Worker Agents** (`src/aegis/agents/worker.py`): Execute work items via specialized agents
- **Specialized Agents**: Triage, Planner, Worker (coder), Reviewer, Merger
- **Execution Model**: Each task runs in an isolated git worktree (`_worktrees/task-<ID>`)

### Data Flow

```
Asana Task (Ready Queue)
  ↓ (Syncer Agent polls)
Master DB (work_queue table)
  ↓ (Master Process schedules)
Worker Agent (idle → busy)
  ↓ (spawns appropriate agent)
Specialized Agent (Triage/Planner/Worker/etc.)
  ↓ (executes in worktree)
Result → Asana Update (section change, comments)
```

### Key Components

**Database Layer** (`src/aegis/database/`):
- **master_models.py**: Work queue and agent pool tables (SQLAlchemy)
- **project_models.py**: Per-project execution history
- **session.py**: Database session management with project-specific routing

**Infrastructure** (`src/aegis/infrastructure/`):
- **AsanaService**: High-level Asana operations (tasks, dependencies, custom fields)
- **WorktreeManager**: Git worktree lifecycle (create, hydrate, cleanup)
- **MemoryManager**: File-based memory storage with locking and compaction
- **PIDManager**: Process locking to prevent concurrent orchestrators

**Agent System** (`src/aegis/agents/`):
- **base.py**: Abstract agent contract (execute(), get_prompt())
- All agents inherit from `BaseAgent` and wrap `claude-code` CLI
- Agents return `AgentResult` with next section, comment, and metadata

**Orchestrator** (`src/aegis/orchestrator/`):
- **master.py**: Spawns syncers and worker pool, schedules work
- **dispatcher.py**: Legacy event loop (being replaced by master.py)

**Dashboard** (`src/aegis/dashboard/`):
- Streamlit app showing syncer logs, work queue, agent status

## Project Structure

- **Configuration**: `.env`, `aegis_config.json`, `schema/asana_config.json`
- **Memory Files**: `swarm_memory.md` (global context), `user_preferences.md`
- **Agent Prompts**: `prompts/` directory (triage.md, planner.md, worker.md, etc.)
- **Tools**: `tools/sync_asana_project.py`, `tools/get_project_gid.py`

## Development Guidelines

### Python Style
- **Python Version**: 3.12+ (requires-python = ">=3.11")
- **Type Checking**: Fully typed (strict mode), use Pydantic v2 models
- **Async**: Use `asyncio` for I/O bound operations (Asana API, subprocess management)
- **Path Handling**: Always use `pathlib.Path` (never raw strings)
- **Logging**: Use `structlog` for structured logging

### Error Handling
- **Graceful Degradation**: Log errors, don't crash the daemon
- **Agent Failures**: Agents should return error results, not raise exceptions
- **Process Monitoring**: Master process auto-restarts crashed syncers/workers

### Testing
- **Markers**: Use `@pytest.mark.integration` for integration tests
- **Async Tests**: Handled via `pytest-asyncio` (asyncio_mode = "auto")
- **Fixtures**: See `tests/conftest.py` and `tests/agents/conftest.py`
- **Skip Patterns**: Tests requiring Asana credentials skip when env vars missing

### Agent Development
- Inherit from `BaseAgent` in `src/aegis/agents/base.py`
- Implement: `name`, `status_emoji`, `target_type`, `get_prompt()`, `execute()`
- Agents receive `AsanaTask` or `AsanaProject` as input
- Return `AgentResult` with: next section, comment text, success flag
- Store prompts in `prompts/<agent_name>.md`

### Database Patterns
- **Master DB**: Shared across all projects (work queue, agent pool)
- **Project DBs**: Per-project execution history (`{project_path}/.aegis/project.db`)
- Use `get_db_session(project_gid=None)` for master, `get_db_session(project_gid=gid)` for project
- All models use SQLAlchemy ORM with declarative base

## Key Design Principles

1. **Asana is the UI**: Users interact via Asana tasks and boards, not CLI
2. **Worktree Isolation**: Each task gets a fresh git worktree to avoid conflicts
3. **Stateless Agents**: Agents don't maintain state; all state lives in Asana or DB
4. **Process Supervision**: Master process monitors and restarts failed agents
5. **Cost Tracking**: All agent execution tracks tokens and costs
6. **Human-in-the-Loop**: "Clarification Needed" state for ambiguous requirements
