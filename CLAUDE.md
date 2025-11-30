# Claude Code Guidelines for Aegis

## Commands

- **Start Orchestrator**: `aegis start` (or `aegis start --daemon`)
- **Stop Orchestrator**: `aegis stop`
- **Check Status**: `aegis status`
- **Sync Asana Schema**: `python tools/sync_asana_project.py --project <GID>`
- **Run Tests**: `pytest`
- **Type Check**: `pyright`
- **Format/Lint**: `ruff check .`

## Architecture Context

Aegis is an **Asana-driven agent swarm**.
- **State Store**: Asana is the source of truth.
- **Orchestrator**: A Python daemon (`src/aegis/orchestrator/dispatcher.py`) polls Asana.
- **Agents**: Specialized classes in `src/aegis/agents/` that wrap `claude-code`.
- **Execution**: Agents run in **isolated git worktrees** (`_worktrees/task-<ID>`).

## Key Files

- `src/aegis/orchestrator/dispatcher.py`: Main event loop.
- `src/aegis/infrastructure/asana_service.py`: Asana logic.
- `src/aegis/agents/base.py`: Base agent class.
- `swarm_memory.md`: Global context.

## Style Guide

- **Python**: 3.12+, fully typed (strict), Pydantic v2.
- **Async**: Use `asyncio` for I/O bound operations.
- **Error Handling**: Graceful degradation, log errors, never crash the daemon.
- **Path Handling**: Use `pathlib.Path`.
