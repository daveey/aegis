# Aegis System Architecture - Detailed Summary

**Generated**: 2025-11-29
**Version**: 2.0 (Master Process Architecture)

---

## Executive Summary

Aegis is an autonomous software development system that uses Asana as its user interface and state management layer. The system orchestrates a "swarm" of specialized AI agents (powered by Claude Code) to handle the complete software development lifecycle: triage, planning, implementation, review, and merging.

**Core Innovation**: Asana projects become executable task queues. Moving a task card between sections triggers agent execution. All state (status, assignments, results) lives in Asana, making the system observable and controllable via a familiar project management UI.

---

## System Architecture

### 1. Three-Tier Process Model

```
┌─────────────────────────────────────────────────────────┐
│                    Master Process                        │
│  - Spawns and monitors Syncers and Workers              │
│  - Manages work queue (SQLite DB)                       │
│  - Handles process supervision and restarts             │
└──────────────────┬────────────────────┬─────────────────┘
                   │                    │
          ┌────────▼────────┐  ┌───────▼───────────┐
          │ Syncer Agents   │  │  Worker Agents    │
          │ (per project)   │  │  (pool of N)      │
          └────────┬────────┘  └───────┬───────────┘
                   │                    │
                   │                    │
          ┌────────▼─────────────────────▼──────────┐
          │         Specialized Agents              │
          │  Triage, Planner, Worker, Reviewer, etc.│
          └─────────────────────────────────────────┘
```

#### 1.1 Master Process (`src/aegis/orchestrator/master.py`)

**Responsibilities**:
- Spawn one **Syncer Agent** per tracked Asana project
- Spawn a pool of **Worker Agents** (default: 2)
- Monitor subprocess health and auto-restart on failure
- Maintain PID files and handle graceful shutdown

**Key Design Decisions**:
- **Process Isolation**: Each Syncer and Worker runs as a subprocess for fault isolation
- **Logging**: Syncer output redirected to `logs/sessions/{session_id}.log`
- **Supervision**: Main loop polls subprocess status every 1 second
- **Database**: Uses master SQLite DB (`~/.aegis/master.db`) for work queue and agent pool

**Implementation Details**:
```python
# Master spawns syncers with dedicated log files
cmd = [sys.executable, "-m", "aegis.agents.syncer",
       "--project-gid", project_gid, "--session-id", session_id]
proc = await asyncio.create_subprocess_exec(*cmd, stdout=log_file, stderr=log_file)

# Workers managed in pool with DB state tracking
await self._spawn_worker(f"worker-{i}")
# Workers query DB for assigned work
```

#### 1.2 Syncer Agents (`src/aegis/agents/syncer.py`)

**Responsibilities**:
- Poll assigned Asana project every `poll_interval_seconds` (default: 30s)
- Sync task metadata to project-specific DB (`.aegis/project.db`)
- Detect tasks needing agent attention (e.g., in "Ready Queue")
- Create **Work Queue Items** in master DB

**Key Design Decisions**:
- **Per-Project Database**: Each project gets its own SQLite DB to avoid schema conflicts
- **Stateless Polling**: No in-memory caching; always fetch fresh state from Asana
- **Work Queue Population**: Syncer writes to master `work_queue` table; Master schedules to Workers

**Data Flow**:
```
Asana Project Tasks → Syncer Polls → Project DB (sync state)
                                   ↓
                     Master DB work_queue (new work items)
                                   ↓
                     Master Process schedules → Worker Agent
```

#### 1.3 Worker Agents (`src/aegis/agents/worker.py`)

**Responsibilities**:
- Poll master DB for assigned work items
- Instantiate the correct specialized agent (Triage, Planner, etc.)
- Execute agent in isolated git worktree
- Report results back to Asana and DB

**Key Design Decisions**:
- **Pull Model**: Workers query DB for work rather than receiving push notifications
- **Agent Factory**: Workers dynamically import and instantiate agent classes
- **Status Tracking**: Worker updates `agent_pool` table (idle → busy → idle)

### 2. Data Architecture

#### 2.1 Database Layer

**Master Database** (`~/.aegis/master.db`):
- **work_queue**: Pending work items (agent_type, resource_id, priority, status)
- **agent_pool**: Running workers (agent_id, status, current_work_item_id, heartbeat)

**Project Databases** (`{project_path}/.aegis/project.db`):
- **projects**: Project metadata (name, portfolio_gid, last_synced_at)
- **tasks**: Task state mirror from Asana (gid, name, section, agent, status)
- **task_executions**: Historical execution log (task_gid, agent_type, started_at, result)

**Session Management** (`src/aegis/database/session.py`):
```python
# Routing logic: project_gid determines which DB to connect to
def get_db_session(project_gid: str | None = None) -> Session:
    if project_gid is None:
        # Master DB
        url = f"sqlite:///{Path.home()}/.aegis/master.db"
    else:
        # Project-specific DB
        project = tracker.get_project(project_gid)
        url = f"sqlite:///{project['local_path']}/.aegis/project.db"
```

**Key Design Decision**: Two-tier DB architecture allows:
- Master to track global work queue and agent pool
- Projects to maintain independent execution history
- Schema isolation (projects can have custom fields)

#### 2.2 State Store: Asana as Source of Truth

**Asana Schema** (`schema/asana_config.json`):

**Sections (Workflow States)**:
1. **Drafts**: User-created tasks (not yet processed)
2. **Clarification Needed**: Agent needs user input
3. **Planning**: Planner agent designs solution
4. **Ready Queue**: Trigger for Worker execution
5. **In Progress**: Agent actively working
6. **Review**: QA and testing phase
7. **Merging**: Integration to main branch
8. **Done**: Completed tasks

**Custom Fields**:
| Field | Type | Purpose |
|-------|------|---------|
| Agent | Single Select | Which agent to run (Triage, Planner, Worker, etc.) |
| Swarm Status | Single Select | Execution state (Idle, Running, Blocked, Complete) |
| Session ID | Text | Continuity for multi-turn agent sessions |
| Cost | Number | Total spend in USD |
| Max Cost | Number | Hard limit (default: $2.00) |
| Merge Approval | Single Select | Safety gate (Auto-Approve, Manual Check, Approved) |
| Worktree Path | Text | Path to git worktree for this task |

**AsanaService** (`src/aegis/infrastructure/asana_service.py`):
High-level wrapper providing:
- Task CRUD with custom field access
- Dependency checking (blocks agent execution if dependencies incomplete)
- Section transitions with validation
- Comment formatting per agent persona

### 3. Agent System

#### 3.1 Base Agent Contract (`src/aegis/agents/base.py`)

All agents inherit from `BaseAgent` and must implement:

```python
class BaseAgent(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Agent identifier (e.g., 'triage_agent')"""

    @property
    @abstractmethod
    def status_emoji(self) -> str:
        """UI emoji (e.g., '🔍' for Triage)"""

    @property
    @abstractmethod
    def target_type(self) -> AgentTargetType:
        """TASK or PROJECT"""

    @abstractmethod
    def get_prompt(self, target: AsanaTask | AsanaProject) -> str:
        """Generate Claude Code CLI prompt"""

    @abstractmethod
    async def execute(self, target, **kwargs) -> AgentResult:
        """Main execution logic"""
```

**Agent Execution Flow**:
1. Agent reads task from Asana via `AsanaService`
2. Generates prompt by loading template from `prompts/{agent_name}.md`
3. Injects task context (title, description, comments, memory)
4. Spawns `claude-code` CLI subprocess with prompt
5. Parses output and extracts result
6. Returns `AgentResult` with next section, comment, and metadata
7. Updates Asana task (section, custom fields, add comment)

#### 3.2 Specialized Agents

**Triage Agent** (`src/aegis/agents/triage.py`):
- **Purpose**: Analyze requirements, assess clarity
- **Input**: Task in "Ready Queue" with Agent=Triage
- **Actions**:
  - If clear → Route to Planner (or Worker if trivial)
  - If unclear → Move to "Clarification Needed", post questions
  - If duplicate → Link to existing task, close
- **Output**: Updated Agent field, next section

**Planner Agent** (`src/aegis/agents/planner.py`):
- **Purpose**: Design architecture and implementation plan
- **Input**: Task in "Planning" section
- **Actions**:
  - Generate technical design
  - Consider trade-offs and alternatives
  - Post plan as comment
  - Route to Worker
- **Output**: Plan comment, Agent=Worker, section=Ready Queue

**Worker Agent** (Coder) (`src/aegis/agents/worker.py`):
- **Purpose**: Implement code changes
- **Input**: Task in "Ready Queue" with Agent=Worker
- **Actions**:
  - Create git worktree (`_worktrees/task-{gid}`)
  - Run `uv sync` to hydrate dependencies
  - Execute Claude Code CLI with coding prompt
  - Run tests, commit changes
  - Push branch
- **Output**: Git branch with changes, section=Review
- **Key Implementation**: Runs in isolated worktree to prevent conflicts

**Reviewer Agent** (`src/aegis/agents/reviewer.py`):
- **Purpose**: QA and safety checks
- **Input**: Task in "Review" section
- **Actions**:
  - Checkout branch in worktree
  - Run full test suite
  - Perform code quality checks
  - Approve or request changes
- **Output**: Review comment, route to Merging or back to Worker

**Merger Agent** (`src/aegis/agents/merger.py`):
- **Purpose**: Safely integrate to main branch
- **Input**: Task in "Merging" section
- **Actions**:
  - Create staging worktree
  - Merge feature branch to staging
  - Run final test pass
  - If approved: merge to main, push, cleanup worktrees
  - If failed: report error, rollback
- **Output**: Merged code or error report

#### 3.3 Claude Code Integration

Agents wrap the `claude-code` CLI:

```python
# Agent constructs prompt from template + context
prompt = self.get_prompt(task)

# Spawn Claude Code subprocess
proc = subprocess.run(
    ["claude-code", "--prompt", prompt],
    cwd=worktree_path,
    capture_output=True,
    text=True,
    timeout=timeout_seconds
)

# Parse structured output (JSON or markdown)
result = self._parse_output(proc.stdout)
```

**Cost Tracking**:
- Each agent execution logs tokens and costs
- Stored in `task_executions` table and Asana "Cost" field
- Hard limit enforced via "Max Cost" field

### 4. Worktree Management

#### 4.1 Git Worktree Isolation

**Problem**: Multiple agents working on different tasks in the same repo causes conflicts.

**Solution**: Each task executes in an isolated git worktree.

**WorktreeManager** (`src/aegis/infrastructure/worktree_manager.py`):

```python
def create_worktree(self, task_gid: str) -> Path:
    worktree_path = self.worktree_dir / f"task-{task_gid}"
    branch_name = f"feat/task-{task_gid}"

    # Create worktree with new branch
    subprocess.run([
        "git", "worktree", "add", "-b", branch_name,
        str(worktree_path)
    ], cwd=self.repo_root)

    # Hydrate dependencies
    subprocess.run([self.hydration_command], cwd=worktree_path)

    # Symlink .env from root
    (worktree_path / ".env").symlink_to(self.repo_root / ".env")

    return worktree_path
```

**Lifecycle**:
1. **Creation**: Worker creates worktree before spawning agent
2. **Execution**: Agent runs all commands in worktree context
3. **Cleanup**: Merger deletes worktree after successful merge

**Key Design Decisions**:
- **Branch Naming**: `feat/task-{gid}` for easy tracking
- **Hydration**: Run `uv sync` to ensure dependencies installed
- **Environment Sharing**: Symlink `.env` so agents have API keys
- **Orphan Detection**: Master scans for worktrees without active tasks and deletes

### 5. Memory and Context Management

#### 5.1 Memory Store

**swarm_memory.md**:
- Global project context (architecture, decisions, conventions)
- Updated by Documentation Agent
- Injected into all agent prompts

**user_preferences.md**:
- User style guides and rules
- Accumulated from clarification responses
- Persistent across tasks

**MemoryManager** (`src/aegis/infrastructure/memory_manager.py`):
- File-based locking via `fcntl` (POSIX) / `msvcrt` (Windows)
- Automatic compaction when >20k tokens
- Thread and process-safe

```python
class MemoryManager:
    def append(self, entry: str):
        with self._lock():
            self.memory_file.write(f"\n{entry}\n")
            self._maybe_compact()

    def _maybe_compact(self):
        content = self.memory_file.read_text()
        if count_tokens(content) > 20000:
            # Summarize with LLM, keep only recent
            summarized = self._summarize(content)
            self.memory_file.write_text(summarized)
```

#### 5.2 Session Continuity

**Session ID**: UUID stored in Asana custom field

**Purpose**:
- Link multi-turn agent conversations
- Resume interrupted work
- Track cost per session

**Reset Logic**:
- When Agent field changes, system clears Session ID
- New agent gets fresh session

### 6. Infrastructure Services

#### 6.1 PID Manager (`src/aegis/infrastructure/pid_manager.py`)

**Purpose**: Prevent multiple orchestrator instances

```python
class PIDManager:
    def acquire_lock(self, process_name: str):
        pid_file = self.pid_dir / f"{process_name}.pid"

        if pid_file.exists():
            old_pid = int(pid_file.read_text())
            if self._is_process_alive(old_pid):
                raise PIDLockError("Already running")
            else:
                logger.warning("stale_pid_detected", old_pid=old_pid)

        pid_file.write_text(str(os.getpid()))
```

**Stale PID Handling**:
- Check if PID exists in process table
- If dead, reclaim lock
- Prevents deadlock from crashed processes

#### 6.2 Dashboard (`src/aegis/dashboard/app.py`)

**Streamlit UI** showing:
- **Syncer Logs**: Tail recent log entries per project
- **Work Queue**: Pending/assigned/completed work items
- **Agent Pool**: Worker status (idle/busy), current task
- **Metrics**: Tasks completed, costs, execution times

**Data Source**: Reads master DB and syncer log files

### 7. Workflow Examples

#### 7.1 Complete Task Flow

```
User: Create task "Add user authentication" in Drafts
User: Move to Ready Queue
  ↓
Syncer: Detects task (Section=Ready Queue, Agent=Triage)
Syncer: Creates WorkQueueItem(agent_type=triage, resource_id=task_gid)
  ↓
Master: Assigns work to idle Worker
Worker: Instantiates TriageAgent
Worker: Executes agent.execute(task)
  ↓
TriageAgent: Analyzes requirements
TriageAgent: Returns AgentResult(next_section=Planning, agent=Planner)
  ↓
Worker: Updates Asana (Section→Planning, Agent→Planner, clears Session ID)
Worker: Marks work item as completed
  ↓
Syncer: Detects task (Section=Planning, Agent=Planner)
Syncer: Creates WorkQueueItem(agent_type=planner, resource_id=task_gid)
  ↓
Master: Assigns work to idle Worker
Worker: Instantiates PlannerAgent
PlannerAgent: Designs auth architecture
PlannerAgent: Posts plan as comment
PlannerAgent: Returns AgentResult(next_section=Ready Queue, agent=Worker)
  ↓
Worker: Updates Asana (Section→Ready Queue, Agent→Worker)
  ↓
Syncer: Detects task (Section=Ready Queue, Agent=Worker)
Syncer: Creates WorkQueueItem(agent_type=worker, resource_id=task_gid)
  ↓
Master: Assigns work to idle Worker
Worker: Creates worktree at .aegis/worktrees/task-{gid}
Worker: Runs uv sync
Worker: Instantiates WorkerAgent (coder)
WorkerAgent: Implements auth code
WorkerAgent: Runs tests, commits changes
WorkerAgent: Returns AgentResult(next_section=Review)
  ↓
Worker: Updates Asana (Section→Review)
Worker: Deletes worktree OR preserves for reviewer
  ↓
... (Review, Merging, Done) ...
```

#### 7.2 Dependency Blocking

```
Task A: "Setup database" (In Progress)
Task B: "Create user model" (depends on Task A, in Ready Queue)
  ↓
Syncer: Detects Task B
AsanaService: Checks dependencies
AsanaService: Task A incomplete → Task B blocked
  ↓
Syncer: Skips Task B (logs "Blocked by Task A")
Dashboard: Shows Task B as blocked
  ↓
[Time passes...]
Task A completes, moves to Done
  ↓
Syncer: Re-checks Task B dependencies
AsanaService: All dependencies complete
Syncer: Creates WorkQueueItem for Task B
  ↓
Master: Assigns Task B to Worker
```

### 8. Key Design Principles

1. **Asana as Single Source of Truth**
   - All state lives in Asana or databases
   - Orchestrator is stateless (can restart anytime)
   - Observable: users see agent progress in real-time

2. **Process Isolation**
   - Master, Syncers, Workers run as separate processes
   - Fault isolation: crashed agent doesn't kill orchestrator
   - Worktree isolation: tasks don't interfere with each other

3. **Pull Model**
   - Workers poll for work (no push notifications)
   - Simplifies architecture, avoids IPC complexity
   - Tradeoff: ~1s latency from scheduling to pickup

4. **Graceful Degradation**
   - Agent failures logged, reported to Asana, don't crash daemon
   - Stale PIDs auto-recovered
   - Orphan worktrees cleaned up

5. **Human-in-the-Loop**
   - "Clarification Needed" state pauses automation
   - "Manual Check" merge approval gate
   - Users can modify tasks, agent respects changes

6. **Cost Safety**
   - Per-task cost limits
   - Execution history tracking
   - Dashboard visibility

### 9. Configuration Files

**`.env`**:
```bash
ASANA_ACCESS_TOKEN=...
ASANA_WORKSPACE_GID=...
ASANA_PORTFOLIO_GID=...
ANTHROPIC_API_KEY=...
DATABASE_URL=postgresql://localhost/aegis  # Optional
```

**`aegis_config.json`**:
```json
{
  "hydration_command": "uv sync",
  "poll_interval_seconds": 30,
  "default_max_cost": 2.0,
  "worktree_dir": ".aegis/worktrees"
}
```

**`schema/asana_config.json`**:
- Canonical section list
- Custom field definitions
- Agent routing table

**`{project}/.aegis/projects.json`**:
- List of tracked Asana projects
- Maps project GID to local repo path

### 10. Testing Strategy

**Unit Tests** (`tests/unit/`):
- Database CRUD operations
- Asana client mocking
- Config loading

**Integration Tests** (`tests/integration/`):
- End-to-end flows with mock agents
- Database relationships
- CLI commands

**Agent Tests** (`tests/agents/`):
- Blocker detection
- Routing logic
- Prompt generation

**Markers**:
```python
@pytest.mark.integration  # Requires DB setup
@pytest.mark.asyncio      # Async test
```

**Skip Patterns**:
```python
@pytest.mark.skipif(not has_asana_creds(), reason="No Asana credentials")
```

### 11. Observability

**Logging**:
- **Structured Logs**: `structlog` with JSON output
- **Syncer Logs**: Per-project session logs in `logs/sessions/`
- **Master Logs**: Combined output to console/file

**Dashboard**:
- Real-time work queue view
- Agent status and heartbeats
- Cost tracking
- Recent log tail per syncer

**Asana Comments**:
- Agents post updates with emoji prefixes
- Timestamped execution logs
- Error reports with stack traces

### 12. Future Enhancements (Not Yet Implemented)

- **Ray Integration**: Distribute workers across multiple machines
- **Vector Database**: Qdrant for code search and context retrieval
- **PostgreSQL**: Replace SQLite for multi-machine setups
- **Redis**: Pub/sub for real-time work notifications
- **Webhook Support**: Asana webhooks to replace polling
- **Web UI**: Enhanced dashboard with task creation

---

## File Structure Reference

```
aegis/
├── src/aegis/
│   ├── agents/
│   │   ├── base.py              # Abstract agent class
│   │   ├── syncer.py            # Asana → DB sync
│   │   ├── worker.py            # Work queue consumer
│   │   ├── triage.py            # Requirements analysis
│   │   ├── planner.py           # Architecture design
│   │   ├── reviewer.py          # QA and testing
│   │   ├── merger.py            # Safe merge protocol
│   │   └── documentation.py     # Knowledge management
│   ├── asana/
│   │   ├── client.py            # Low-level Asana API
│   │   └── models.py            # Pydantic models
│   ├── database/
│   │   ├── master_models.py     # Work queue, agent pool
│   │   ├── project_models.py    # Task execution history
│   │   ├── session.py           # DB routing logic
│   │   └── crud.py              # Database operations
│   ├── infrastructure/
│   │   ├── asana_service.py     # High-level Asana ops
│   │   ├── worktree_manager.py  # Git worktree lifecycle
│   │   ├── memory_manager.py    # Memory store locking
│   │   └── pid_manager.py       # Process locking
│   ├── orchestrator/
│   │   ├── master.py            # Main orchestrator
│   │   └── dispatcher.py        # Legacy (deprecated)
│   ├── dashboard/
│   │   └── app.py               # Streamlit UI
│   ├── core/
│   │   ├── models.py            # Shared models
│   │   └── tracker.py           # Project tracking
│   ├── config.py                # Pydantic settings
│   └── cli.py                   # Click commands
├── prompts/                      # Agent system prompts
├── schema/                       # Asana schema config
├── tools/                        # Utility scripts
├── tests/                        # Test suite
├── .env                          # Environment secrets
├── aegis_config.json             # App configuration
├── swarm_memory.md               # Global context
├── user_preferences.md           # User rules
└── pyproject.toml                # Python dependencies
```

---

## Conclusion

Aegis implements a robust, observable, and autonomous software development system. By treating Asana as both UI and state store, it provides a familiar interface for users while enabling sophisticated multi-agent orchestration behind the scenes. The three-tier process model (Master → Syncers/Workers → Specialized Agents) provides fault isolation and scalability, while git worktree isolation ensures safe concurrent task execution.

The system is designed for personal use (single developer) but architected to scale to team settings via PostgreSQL and distributed workers. All design decisions prioritize observability, reliability, and human control.
