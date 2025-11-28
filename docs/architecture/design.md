# Design Document: Personal LLM Agent Swarm (Aegis)

## 1. Executive Summary

This system, named **Aegis**, automates software development tasks using a "Swarm" of LLM agents. **Asana serves as the primary User Interface and State Store**. A local Python orchestrator manages the lifecycle of tasks, dispatching them to specific `claude-code` CLI instances (Agents) based on their state.

The system is designed to be **autonomous**, **reliable**, and **observable**. It strictly separates "Executable" work from "Clarification" states and implements robust git hygiene to prevent repository corruption.

---

## 2. System Architecture

### 2.1 Core Components

**The Interface (Asana)**: Stores state, instructions, and communication history.

**The Orchestrator (Python Daemon)**:
- **Process Control**: Uses PID Locking to ensure singleton execution.
- **Startup Scan**: On boot, checks for "zombie" tasks in In Progress.
- **Pruning**: Deletes orphaned folders in `_worktrees/` that do not match active tasks.
- **Event Loop**: Polls Asana for state changes (Events).
- **Dependency Filter**: Checks Asana's native dependency graph. Skips blocked tasks automatically to prevent execution order errors.
- **Internal Scheduler**: Manages cron-like execution for maintenance agents.
- **Optimized Polling**: Tracks blocked tasks via `subtask_gid` mapping to avoid API rate limits.
- **Workspace Manager**: Manages ephemeral git worktrees.
  - **Hydration**: Runs `uv sync` (or config command).
  - **Environment Injection**: Symlinks the root `.env` file into the worktree so code runs correctly.
- **Memory Lock (Mutex)**: A file-based locking mechanism (`swarm_memory.lock`) to serialize write access to `swarm_memory.md`.

**The Agents (Claude Code Wrappers)**:
- **Triage Agent**: Planning & Requirements gathering.
- **Planner Agent**: Iterative architecture design (Plan → Critique → Fix).
- **Worker Agent**: Execution (Coding, Terminal commands).
- **Review Agent**: QA & Safety checks.
- **Merger Agent**: Integrates verified code and cleans up worktrees using Safe Merge protocol in an Isolated Worktree.
- **Refactor Detector**: Periodic maintenance scanner.
- **Code Consolidation Agent**: Scans for duplication and proposes DRY improvements.
- **Feature Suggestor**: Creative partner for ideation.
- **Documentation Agent**: Maintains knowledge base and user preferences.
- **Watchdog Agent**: Meta-monitor that detects hung processes and enforces cost limits.

**Memory Store (Filesystem)**:
- `swarm_memory.md`: Global project context (High-Level Decisions Only).
- `user_preferences.md`: Accumulated user rules and style guides.
- `logs/`: Detailed execution logs for observability.
- `swarm_state.json`: Persists scheduler timestamps and `blocked_tasks` map.
- `prompts/*.md`: External storage for Agent System Prompts.

---

## 3. Asana Schema Configuration

The system relies on specific **Custom Fields** and **Project Structure** to function.

### 3.1 Project Structure (Canonical List)

The following sections are mandatory:

1. **Drafts** (Passive holding area)
2. **Clarification Needed** (Waiting for User)
3. **Planning** (Planner Agent)
4. **Ready Queue** (Trigger for Workers)
5. **In Progress** (Running)
6. **Review** (QA)
7. **Merging** (Integration)
8. **Done**

### 3.2 Custom Fields

| Field Name | Type | Options | Purpose |
|------------|------|---------|---------|
| **Agent** | Single Select | Triage (Default), Planner, Worker, Reviewer, Merger, Refactor, Consolidator, Ideation, Documentation | Active Persona. Default value must be set to **Triage** in Asana. |
| **Swarm Status** | Single Select | Idle, Running, Blocked, Complete | Execution State. |
| **Session ID** | Text | (UUID) | Continuity. Must be reset when Agent changes. |
| **Cost** | Number | (USD) | Tracks cost. |
| **Max Cost** | Number | (USD) | Default: 2.00. Hard limit. |
| **Merge Approval** | Single Select | Auto-Approve (Default), Manual Check, Approved | Safety gate. |
| **Worktree Path** | Text | (Path) | Path to ephemeral worktree. |

### 3.3 Schema Synchronization Strategy

Since projects evolve, we will not manually manage sections. A script `tools/sync_asana_sections.py` will enforce the state defined in **3.1**.

- **Config Source**: `schema/asana_config.json` (Source of Truth).
- **Sync Logic**:
  - **Fetch**: Get current sections of a target project.
  - **Compare**: Match against the Canonical List.
  - **Create**: If a canonical section is missing, create it.
  - **Reorder**: Ensure sections appear in the exact order defined above.
  - **Handling Unknowns**: If a project has sections not in the list (e.g., "Old Stuff"), log a warning but do not delete them to prevent data loss.
- **Scope**: The script should accept a `--project_id` or `--portfolio_id` to apply changes in batch.

### 3.4 Configuration Schema (aegis_config.json)

```json
{
  "hydration_command": "uv sync",
  "default_max_cost": 2.00,
  "poll_interval_seconds": 10,
  "watchdog_interval_seconds": 60,
  "silent_timeout_seconds": 300,
  "memory_file": "swarm_memory.md",
  "schedules": {
    "refactor_detector": "weekly",
    "code_consolidator": "weekly"
  }
}
```

### 3.5 Environment Variables (.env)

```bash
ASANA_PAT="1/1234..."
ASANA_WORKSPACE_ID="123..."
ASANA_PROJECT_ID="456..."
ANTHROPIC_API_KEY="sk-ant..."
# Optional: Overrides
AEGIS_DEBUG_MODE="true"
```

---

## 4. Information Flow & State Machine

### 4.1 The Happy Path (Execution)

1. User drafts a task in **Drafts**.
2. User moves task to **Ready Queue**.
3. Orchestrator detects Task (Section: **Ready Queue**, Agent: **Triage**).
4. **Dependency Check**: Orchestrator checks if task is blocked by incomplete dependencies.
   - **If Blocked**: Task is **Skipped** (remains in Ready Queue, logs "Skipped: Blocked by [Task Name]" to dashboard).
   - **If Clear**: Proceed.
5. Orchestrator moves task to **In Progress**, sets Status to **Running**.
6. **Triage Agent** runs:
   - Analyzes request.
   - **Action**: Updates Agent to **Planner**.
   - **System Action**: Clears Session ID.
   - Moves task to **Planning**.
   - Status to **Idle**.
7. Orchestrator detects Task (Section: **Planning**, Agent: **Planner**).
8. **Planner Agent** runs:
   - **Action**: Posts Final Plan to Comments.
   - Updates Agent to **Worker**.
   - **System Action**: Clears Session ID.
   - Moves task to **Ready Queue**.
   - Status to **Idle**.
9. Orchestrator detects Task (Section: **Ready Queue**, Agent: **Worker**).
10. **Dependency Check**: Re-confirms dependencies are still clear.
11. **System Action 1**: Creates git worktree at `_worktrees/task-<ID>`.
12. **System Action 2 (Hydration)**: Runs `hydration_command`.
13. **System Action 3 (Env)**: Symlinks `.env` to `_worktrees/task-<ID>/.env`.
14. **Worker Agent** runs (inside Worktree):
    - Executes code on isolated branch `feat/task-<ID>`.
    - **Rebase Step**: Runs `git fetch origin main` and `git merge origin/main`.
    - **Action**: Updates Agent to **Reviewer**.
    - **System Action**: Clears Session ID.
    - Moves to **Review**.
15. **Review Agent** runs (inside Worktree):
    - Runs tests.
    - **Outcome**: Success.
    - **Action**: Updates Agent to **Merger**.
    - **System Action**: Clears Session ID.
    - Moves to **Merging**.
16. **Merger Agent** runs (inside Isolated Worktree):
    - **Context**: `_worktrees/merger_staging`.
    - **Pre-Check**: Verifies Merge Approval.
    - **Safe Merge**: Fetch main, Merge `feat/task-<ID>`, Run Tests, Push.
    - **System Action (Order Critical)**:
      1. Delete Worker Worktree `_worktrees/task-<ID>` (Unlocks branch).
      2. Delete Git Branch `feat/task-<ID>`.
      3. Move Task to **Done**.

### 4.2 The Clarification Loop (The "Blocked" State)

1. Orchestrator picks up task.
2. **Triage Agent** runs.
3. **Outcome**: Request is vague.
4. **Action**:
   - Creates a **Subtask** assigned to User.
   - Moves Main Task to **Clarification Needed**.
   - Sets Status to **Blocked**.
5. **Orchestrator Behavior (Optimized Polling)**:
   - Stores mapping `{main_task_gid: subtask_gid}` in `swarm_state.json`.
   - Only polls these specific subtask GIDs.
6. User completes Subtask.
7. Orchestrator detects completion:
   - Moves Main Task back to **Ready Queue**.
   - Sets Agent back to **Triage**.
   - Resets Session ID.

### 4.3 The Preference Update Loop (Learning Mechanism)

1. User creates a task in **Drafts** with title prefix `"Preference:"` OR sets Agent to **Documentation**.
2. User moves task to **Ready Queue**.
3. Orchestrator dispatches to **Documentation Agent**.
4. **Documentation Agent** runs:
   - Updates `user_preferences.md`.
   - **Memory Compaction**: Checks if `swarm_memory.md` > 20k tokens. If so, summarizes top 50% into a "History" block.
   - **Outcome**: Updates file, comments "Preference recorded", and moves to **Done**.

### 4.4 Communication Protocol (Asana Comments)

To keep the Asana history readable and the user interface clean, all agents must adhere to a strict comment template.

**The "Concise & Critical" Standard**:
- **No Wall of Text**: Summaries must be under 50 words.
- **Visual Status**: Use emojis to signal outcome immediately.
- **Deep Linking**: Every comment must link to the granular logs in the Dashboard.

**Template Format**:

```
**[Agent Name]** {Status_Emoji}
{Concise Summary of Action, e.g., "Implemented JWT middleware and added 3 unit tests."}

**Critical Details:**
* {Detail 1: e.g., "Created file: src/middleware/auth.ts"}
* {Detail 2: e.g., "Cost: $0.15"}

🔗 [View Session Log](http://localhost:8501/session/{session_id})
```

### 4.5 Scheduled Maintenance Loops (Cron Agents)

1. **Orchestrator Loop**: Checks timestamp `last_run_<agent>` in `swarm_state.json`.
2. **Trigger Condition**: If `(Current Time - Last Run) > Config Interval`:
   - **Ephemeral Task Creation**:
     - Orchestrator creates a task in **In Progress**.
     - Title: `[System] Auto-Run: <Agent Name>`
   - **Agent Execution**:
     - The Agent runs using the ephemeral task for logging context.
   - **Cleanup**:
     - The Ephemeral Task is marked **Done**.
     - `last_run_<agent>` timestamp is updated.

---

## 5. Agent Definitions & Contracts

### 5.1 Triage Agent (The Requirements Analyst)

- **Input State**: Ready Queue, Agent=Triage
- **Output**: Clear Request Summary in Comments.
- **Transition**: Success → Planner. Vague → Blocked.

### 5.2 Planner Agent (The Architect)

- **Input State**: Planning, Agent=Planner
- **Logic**: Iterative Plan → Critique → Refine.
- **Output**: Final Plan in Comments.
- **Transition**: Success → Worker.

### 5.3 Worker Agent (The Builder)

- **Input State**: Ready Queue, Agent=Worker
- **Context**: `_worktrees/task-<ID>` (Hydrated + .env).
- **Logic**: Rebase before handoff.
- **Output**: Code changes.
- **Transition**: Success → Reviewer. Fail → Blocked.

### 5.4 Reviewer Agent (The Gatekeeper)

- **Input State**: Review, Agent=Reviewer
- **Output**: Test results.
- **Transition**: Pass → Merger. Fail → Worker.

### 5.5 Merger Agent (The Integrator)

- **Input State**: Merging, Agent=Merger
- **Context**: `_worktrees/merger_staging`.
- **Logic**: Check Merge Approval → Safe Merge Protocol.
- **Transition**: Success → Done. Conflict → Blocked.

### 5.6 Refactor Detector (The Janitor)

- **Trigger**: Weekly.
- **Action**: Creates tasks in Drafts.

### 5.7 Code Consolidation Agent (The Optimizer)

- **Trigger**: Weekly.
- **Action**: Creates tasks in Drafts.

### 5.8 Feature Suggestor (The Ideator)

- **Trigger**: User Request.
- **Action**: Suggests ideas in Drafts.

### 5.9 Documentation Agent (The Librarian)

- **Input State**: Ready Queue, Agent=Documentation.
- **Action**: Updates `user_preferences.md`. Compacts Memory.

### 5.10 Watchdog Agent (The Supervisor)

- **Trigger**: Polled every 60s.
- **Checks**: Cost Velocity, Max Cost, Silent Timeout (5m), Stuck Analysis.
- **Action**: Kill process → Blocked.

---

## 6. Implementation Standards & Tooling

- **Package Management**: `uv`.
- **Data Validation**: `pydantic` (v2).
- **Static Analysis**: `pyright` (Strict).
- **Rich Text**: `markdown` + `html2text`.

### 6.1 Asana API Abstraction Layer

**Class Contract**: `src/infrastructure/asana_service.py`

```python
class AsanaService:
    def is_task_blocked(self, task_gid: str) -> bool:
        """
        Checks Asana 'dependencies' field.
        Returns True if any upstream dependency is marked incomplete.
        """
        ...
```

### 6.2 Memory Manager (Locking)

**Class Contract**: `src/infrastructure/memory_manager.py`

```python
class MemoryManager:
    # FileLock implementation
    ...
```

### 6.3 Agent Runtime (Permissions)

- **Required Flag**: `--dangerously-skip-permissions` (or equivalent).
- **Session Management**: Orchestrator must generate **New Session ID** on Agent change to prevent context pollution.

---

## 7. Testing Strategy

- **Unit**: Parser tests, Config validation.
- **Integration**: Mock Asana API (`respx`), Mock CLI (`subprocess`).
- **E2E**: Dry Run Loop with local sandbox.

---

## 8. Aegis CLI Reference

### 8.1 Core Commands

- `aegis start [--daemon]`: Starts Orchestrator. Checks Auth, PID Lock, and "Zombie" tasks. Prunes orphaned worktrees.
- `aegis stop`: Graceful shutdown.
- `aegis status`: Summary table.

### 8.2 Observability

- `aegis logs`: Tail structured logs.
- `aegis dashboard`: Launch Streamlit.

### 8.3 Management

- `aegis sync`: Enforce Asana sections.
- `aegis init`: Generate config files.

### 8.4 Project Bootstrapping (aegis create)

A simplified command to spin up a new Swarm-ready project.

**Command**: `aegis create "<Project Name>"`

**Behavior**:
1. **Project Creation**: Creates a new project in the configured Workspace/Team.
2. **Schema Application**:
   - Creates Canonical Sections.
   - Adds Global Custom Fields.
   - Sets Default Value of Agent field to **Triage**.
3. **Config Update**: Prints `PROJECT_GID`.

---

## 9. Implementation Tasks

### Phase 1: Asana & Configuration

- ☐ Create Project & Fields.
- ☐ Setup `uv` + `pyright`.
- ☐ Implement `AsanaService` with Rich Text Adapters and Dependency Checking.
- ☐ Implement `sync_asana_sections.py` and `aegis create` command.

### Phase 2: The Orchestrator

- ☐ Implement `SwarmDispatcher` with PID Locking, Startup Scan, & Pruning.
- ☐ Implement Optimized Polling (Subtask GID Map) and Dependency Filtering.
- ☐ Worktree Manager: Add `uv sync` and `.env` Symlinking.
- ☐ Implement Session ID Reset logic on agent transition.

### Phase 3: Agent Wrappers

- ☐ Worker: Add `git fetch/merge` pre-handoff step.
- ☐ Merger: Add `_worktrees/merger_staging` isolation & no-commit protocol.
- ☐ Watchdog: Add Cost, Silent Timeout, & Stuck checks.
- ☐ Runtime: Enforce `--dangerously-skip-permissions` flag.

### Phase 4: Observability

- ☐ Structured Logging & Dashboard with Deep Linking.
- ☐ Documentation Agent: Add Memory Compactor logic.

---

## 10. Documentation Artifacts for LLMs

- `LLM_ARCHITECTURE.md`
- `prompts/README.md`
- `schema/asana_objects.json`
- `tools_manifest.json`

---

## 11. Completion Criteria

- **Zero-Touch Loop**: Ready → Done autonomously.
- **Reliability**: No broken main builds (Safe Merge). No stale branch conflicts (Worker Rebase).
- **Safety**: Cost caps enforced. Interactive prompts suppressed.
- **Visibility**: Dashboard reflects real-time state.
- **Fidelity**: Rich text (Bold, Lists, Links) is preserved correctly between Asana and Agents.
