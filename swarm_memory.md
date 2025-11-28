# Aegis Swarm Memory

> **Purpose**: This file stores high-level project context and decisions made by the swarm.
> It is automatically compacted when it exceeds 20k tokens.

## Project Context

**Project**: Aegis - Personal LLM Agent Swarm
**Repository**: /Users/daveey/code/aegis
**Primary Language**: Python 3.11+
**Key Technologies**: Asana API, Claude Code, PostgreSQL

## Architecture Decisions

### 2025-11-28: Initial Swarm Design
- Adopted multi-agent architecture with specialized roles (Triage, Planner, Worker, Reviewer, Merger)
- Using Asana as primary UI and state store
- Git worktrees for task isolation
- Section-based state machine for task flow

## Current State

**Active Features**:
- Infrastructure layer complete (PIDManager, MemoryManager, WorktreeManager, AsanaService)
- Configuration system with aegis_config.json
- Schema definitions for Asana structure

**In Progress**:
- Agent implementations
- New orchestrator with state machine
- CLI updates

## Important Context

### Dependencies
- All agent execution requires Claude Code CLI
- Worktrees require git 2.5+
- Database requires PostgreSQL

### Conventions
- Branch naming: `feat/task-{gid}`
- Worktree location: `_worktrees/task-{gid}/`
- Log files: `logs/aegis.log`
- Session logs: `logs/session-{session_id}.log`

### Known Limitations
- Custom field GID lookup not yet implemented in AsanaService
- Watchdog agent not yet implemented
- Scheduled maintenance agents not yet implemented

---

**Last Updated**: 2025-11-28
**Token Estimate**: ~500
