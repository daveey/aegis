# Aegis Project Structure

This document outlines the file organization of the Aegis system (v2.0).

## Root Directory

- `aegis_config.json`: Main configuration file for the orchestrator.
- `swarm_memory.md`: Global context and high-level decisions for the swarm.
- `user_preferences.md`: User-specific rules and style guides.
- `swarm_state.json`: Persistent state (timestamps, blocked tasks) for the orchestrator.
- `migration_plan.md`: Guide for migrating from v1.0.
- `_worktrees/`: Directory where ephemeral git worktrees are created (git-ignored).

## Source Code (`src/aegis/`)

### `infrastructure/`
Core services that power the system.
- `pid_manager.py`: Enforces singleton execution and handles locking.
- `memory_manager.py`: Thread-safe access to memory files.
- `worktree_manager.py`: Manages the lifecycle of git worktrees.
- `asana_service.py`: High-level interface for Asana interactions.

### `agents/`
Implementation of the specific swarm agents.
- `base.py`: Abstract base class for all agents.
- `triage.py`: Requirements analysis and routing.
- `planner.py`: Architecture and implementation planning.
- `worker.py`: Code execution and testing.
- `reviewer.py`: Code quality and security review.
- `merger.py`: Safe merge protocol integration.
- `documentation.py`: Knowledge base maintenance.

### `orchestrator/`
The central nervous system.
- `dispatcher.py`: Main event loop, polling, and task dispatching logic.

### `asana/`
Low-level API clients and models.
- `client.py`: Raw Asana API client.
- `models.py`: Pydantic models for Asana objects.

## Tools (`tools/`)

- `sync_asana_project.py`: Script to enforce canonical Asana project structure.

## Prompts (`prompts/`)

Markdown files containing the system prompts for each agent.
- `triage.md`
- `planner.md`
- `worker.md`
- `reviewer.md`
- `merger.md`
- `documentation.md`

## Documentation (`docs/`)

- `architecture/`: Design docs and architectural summaries.
- `fixes/`: Documentation on specific bug fixes (legacy).
