# Aegis Refactor Plan - New Swarm Design

## Assessment Summary

The new design requires a significant architectural shift from the current implementation. The core changes include:

1. **Multi-Agent System**: Moving from single "simple_executor" to specialized agents (Triage, Planner, Worker, Reviewer, Merger, etc.)
2. **Git Worktree Isolation**: Each task gets its own git worktree for safe parallel execution
3. **Section-Based State Machine**: Tasks flow through Asana sections (Drafts → Ready Queue → In Progress → Review → Merging → Done)
4. **Custom Field Management**: New Asana custom fields for Agent, Status, Session ID, Cost, Merge Approval, etc.
5. **Memory Management**: File-based locking for swarm_memory.md, user_preferences.md
6. **Dependency Tracking**: Native Asana dependencies with blocking behavior

## Current State vs. New Design

### ✅ Can Be Reused
- **Database Layer**: models.py, session.py, crud.py (minor updates needed)
- **Asana Client**: client.py foundation (needs extension)
- **Shutdown Handler**: utils/shutdown.py (mostly compatible)
- **Logging Infrastructure**: structlog setup
- **Configuration Pattern**: Pydantic Settings (needs extension)

### 🔄 Needs Major Updates
- **Asana Models** (asana/models.py):
  - Add custom_field helper methods
  - Add dependency tracking
  - Add section membership

- **Orchestrator** (orchestrator/main.py):
  - Replace simple task queue with section-based state machine
  - Add worktree lifecycle management
  - Add agent routing based on custom fields
  - Add dependency blocking logic

- **CLI** (cli.py):
  - Simplify to new command structure
  - Remove `work-on` (replaced by continuous `start`)
  - Add `create`, `init`, `sync` commands

### ❌ Needs to Be Created
- **Infrastructure Layer**:
  - `src/infrastructure/asana_service.py` - High-level Asana operations
  - `src/infrastructure/worktree_manager.py` - Git worktree lifecycle
  - `src/infrastructure/memory_manager.py` - File locking for memory files
  - `src/infrastructure/pid_manager.py` - PID locking for singleton orchestrator

- **Agent Definitions**:
  - `src/agents/triage.py`
  - `src/agents/planner.py`
  - `src/agents/worker.py`
  - `src/agents/reviewer.py`
  - `src/agents/merger.py`
  - `src/agents/watchdog.py`
  - `src/agents/documentation.py`
  - `src/agents/maintenance.py` (refactor detector, code consolidator)
  - `src/agents/base.py` - Base agent contract

- **Configuration**:
  - `aegis_config.json` - Main config file
  - `schema/asana_config.json` - Schema definitions

- **Tools**:
  - `tools/sync_asana_sections.py` - Enforce canonical sections

- **Memory Files**:
  - `swarm_memory.md` - Global project context
  - `user_preferences.md` - User rules and preferences
  - `swarm_state.json` - Scheduler timestamps, blocked tasks map

- **Prompts**:
  - `prompts/triage.md`
  - `prompts/planner.md`
  - `prompts/worker.md`
  - `prompts/reviewer.md`
  - `prompts/merger.md`
  - `prompts/documentation.md`

### 🗑️ Can Be Removed/Deprecated
- **orchestrator/agent_client.py** - Replaced by agent definitions
- **orchestrator/display.py** - Keep but simplify
- **orchestrator/prioritizer.py** - Not needed (sections determine order)
- **agents/simple_executor.py** - Replaced by Worker agent
- **agents/agent_service.py** - Replaced by infrastructure/asana_service.py
- **agents/formatters.py** - Move formatting to agent base
- **agents/prompts.py** - Move to prompts/*.md files
- **sync/asana_sync.py** - Keep but move to tools/

## Implementation Strategy

### Phase 1: Foundation (New Infrastructure)
**Goal**: Create the infrastructure layer without breaking existing code

1. Create `src/infrastructure/` directory
2. Implement `AsanaService` with dependency checking
3. Implement `WorktreeManager` with hydration and env symlinking
4. Implement `MemoryManager` with file locking
5. Implement `PIDManager` for singleton orchestrator
6. Create configuration schema files (aegis_config.json, schema/asana_config.json)
7. Update Asana models to support new custom fields
8. Create memory file templates (swarm_memory.md, user_preferences.md)

**Testing**: Unit tests for each infrastructure component

### Phase 2: Agent System
**Goal**: Define agent contracts and implementations

1. Create `src/agents/base.py` with `BaseAgent` contract
2. Create prompt files in `prompts/`
3. Implement core agents:
   - `triage.py`
   - `planner.py`
   - `worker.py`
   - `reviewer.py`
   - `merger.py`
4. Implement support agents:
   - `documentation.py`
   - `watchdog.py`

**Testing**: Mock tests for each agent with sample Asana tasks

### Phase 3: New Orchestrator
**Goal**: Replace current orchestrator with section-based state machine

1. Create new `orchestrator/dispatcher.py` - Main event loop
2. Implement section polling and task detection
3. Implement dependency filtering
4. Implement agent routing (section + custom field → agent)
5. Implement worktree lifecycle:
   - Create worktree on task start
   - Hydrate with `uv sync`
   - Symlink .env
   - Clean up on completion
6. Implement session ID management
7. Implement zombie task detection on startup
8. Implement orphaned worktree pruning

**Testing**: Integration tests with mock Asana API

### Phase 4: CLI & Tools
**Goal**: Update CLI to match new design

1. Create `tools/sync_asana_sections.py`
2. Simplify `cli.py`:
   - Keep: `start`, `stop`, `status`, `logs`, `dashboard`
   - Add: `create`, `init`, `sync`
   - Remove: `do`, `work-on`, `organize`, `plan` (replaced by agent system)
3. Update `aegis start` to use new orchestrator
4. Implement `aegis create` for project bootstrapping
5. Implement `aegis init` for config generation

**Testing**: E2E tests with local Asana sandbox

### Phase 5: Cleanup & Documentation
**Goal**: Remove deprecated code and finalize docs

1. Remove deprecated files
2. Update CLAUDE.md with new architecture
3. Update PROJECT_STRUCTURE.md
4. Create LLM_ARCHITECTURE.md
5. Create prompts/README.md
6. Update test suite
7. Update .env.example

## Detailed File Changes

### New Files to Create

```
src/
  infrastructure/
    __init__.py
    asana_service.py       # High-level Asana operations
    worktree_manager.py    # Git worktree lifecycle
    memory_manager.py      # File locking
    pid_manager.py         # PID locking
  agents/
    base.py                # BaseAgent contract
    triage.py              # Requirements analyst
    planner.py             # Architect
    worker.py              # Builder
    reviewer.py            # Gatekeeper
    merger.py              # Integrator
    documentation.py       # Librarian
    watchdog.py            # Supervisor
    maintenance.py         # Janitor + Optimizer
  orchestrator/
    dispatcher.py          # New main orchestrator

tools/
  sync_asana_sections.py   # Section enforcement

schema/
  asana_config.json        # Schema definitions
  asana_objects.json       # API object examples

prompts/
  README.md
  triage.md
  planner.md
  worker.md
  reviewer.md
  merger.md
  documentation.md
  watchdog.md

aegis_config.json          # Main configuration
swarm_memory.md            # Global context
user_preferences.md        # User preferences
swarm_state.json           # Scheduler state
LLM_ARCHITECTURE.md        # Architecture for LLMs
```

### Files to Update

```
src/aegis/
  asana/models.py          # Add custom field helpers, dependencies
  config.py                # Extend for new config options
  cli.py                   # Simplify and update commands
  database/models.py       # Add session_id, worktree_path fields

tests/
  unit/
    test_infrastructure.py # New infrastructure tests
    test_agents.py         # New agent tests
  integration/
    test_orchestrator.py   # Updated orchestrator tests
```

### Files to Remove

```
src/aegis/
  orchestrator/agent_client.py
  orchestrator/prioritizer.py
  agents/simple_executor.py
  agents/agent_service.py
  agents/formatters.py
  agents/prompts.py
```

## Key Design Decisions

### 1. Worktree Management
- **Location**: `_worktrees/task-{gid}/`
- **Lifecycle**: Create on task start, delete on completion
- **Hydration**: Run `uv sync` after worktree creation
- **Environment**: Symlink root `.env` to worktree `.env`
- **Merger Isolation**: Special `_worktrees/merger_staging/` for safe merges

### 2. Agent Routing
```python
def route_task_to_agent(task: AsanaTask) -> Agent:
    section = get_task_section(task)
    agent_type = get_custom_field(task, "Agent")

    routing_table = {
        ("Ready Queue", "Triage"): TriageAgent,
        ("Planning", "Planner"): PlannerAgent,
        ("Ready Queue", "Worker"): WorkerAgent,
        ("Review", "Reviewer"): ReviewerAgent,
        ("Merging", "Merger"): MergerAgent,
    }

    return routing_table.get((section, agent_type))
```

### 3. Dependency Blocking
```python
def is_task_blocked(task: AsanaTask) -> bool:
    dependencies = asana_client.get_dependencies(task.gid)
    return any(not dep.completed for dep in dependencies)
```

### 4. Session ID Management
- Generate new UUID when agent changes
- Store in custom field "Session ID"
- Use for log file naming and context continuity

### 5. Memory Locking
```python
with memory_manager.lock("swarm_memory.md"):
    # Read/write operations
    pass
```

## Migration Path

### Option A: Big Bang (Recommended)
1. Create all new infrastructure in Phase 1
2. Keep old orchestrator running
3. Switch to new orchestrator in Phase 3
4. Delete old code in Phase 5

**Pros**: Clean break, no compatibility shims
**Cons**: Can't test incrementally

### Option B: Gradual
1. Create new infrastructure alongside old
2. Add feature flag `AEGIS_USE_NEW_ORCHESTRATOR`
3. Run both systems in parallel
4. Gradually migrate agents
5. Remove old system when stable

**Pros**: Can test incrementally
**Cons**: More complex, longer migration period

### Recommendation: Option A (Big Bang)
The design changes are too fundamental for gradual migration. Better to build the new system cleanly and switch over.

## Risk Mitigation

1. **Data Loss**:
   - Back up swarm_memory.md before migration
   - Keep old code in git branch

2. **Asana State Corruption**:
   - Test sync_asana_sections.py thoroughly
   - Always preserve unknown sections (don't delete)

3. **Worktree Leaks**:
   - Implement robust cleanup in shutdown handler
   - Add orphan detection on startup

4. **Concurrent Access**:
   - Use PID locking for orchestrator singleton
   - Use file locking for memory files

5. **Cost Overruns**:
   - Implement Watchdog agent early
   - Add cost tracking to all agent calls

## Next Steps

1. ✅ Review and approve this plan
2. Create Phase 1 infrastructure components
3. Set up test harness for new components
4. Implement agents with prompts
5. Build new orchestrator
6. Update CLI
7. Test end-to-end workflow
8. Migrate and clean up

## Questions to Resolve

1. **Asana Custom Fields**: Do they already exist, or do we need to create them?
2. **Portfolio Structure**: Is there a specific portfolio to use, or create new?
3. **Git Branch Strategy**: Should we use `main` or `master`? (Current seems to use no main branch)
4. **Database Migration**: Keep existing tables or start fresh?
5. **Backward Compatibility**: Any existing tasks in Asana to migrate?

## Estimated Timeline

- **Phase 1 (Foundation)**: 2-3 days
- **Phase 2 (Agents)**: 3-4 days
- **Phase 3 (Orchestrator)**: 2-3 days
- **Phase 4 (CLI)**: 1-2 days
- **Phase 5 (Cleanup)**: 1 day

**Total**: ~10-15 days of development + testing

---

**Status**: Ready for implementation
**Last Updated**: 2025-11-28
