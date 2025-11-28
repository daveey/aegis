# Orchestration Loop Architecture

## Overview

This document describes the main orchestration loop architecture for Aegis - the core event-driven system that coordinates task polling, prioritization, queueing, and agent execution.

## Executive Summary

The orchestration system uses an **asyncio-based dual-loop architecture** with polling for task discovery and intelligent dispatching for execution. The design prioritizes:
- **Reliability**: Graceful error handling and recovery
- **Scalability**: Configurable concurrency with bounded parallelism
- **Observability**: Comprehensive logging and state tracking
- **Graceful Degradation**: Clean shutdown without data loss

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Polling vs Webhooks** | Polling (30s default) | Simpler to implement and debug; webhooks planned for Phase 2+ |
| **Event Loop** | asyncio | Native Python async/await, excellent for I/O-bound workload |
| **Task Queue** | Priority queue with in-memory state | Fast prioritization; database serves as persistent source of truth |
| **Concurrency Model** | Bounded semaphore pattern (5 concurrent tasks default) | Prevents resource exhaustion while maintaining throughput |
| **Error Handling** | Per-task isolation with retry capability | Failures don't cascade; tasks can be retried independently |
| **Shutdown** | Cooperative with timeout enforcement | Graceful completion with forced termination as fallback |

## System Architecture

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      Asana (External)                            │
│  - Portfolio Projects                                            │
│  - Tasks (unassigned, incomplete)                                │
│  - Comments, Attachments, Custom Fields                          │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTPS/REST API
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator.run()                            │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ Initialization Phase                                   │     │
│  │ - Initialize ShutdownHandler                           │     │
│  │ - Install signal handlers (SIGTERM, SIGINT)           │     │
│  │ - Register cleanup callbacks                           │     │
│  │ - Mark orchestrator as running in database             │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                   │
│  ┌─────────────────────┐      ┌──────────────────────┐         │
│  │   Poll Loop         │      │   Dispatch Loop      │         │
│  │   (_poll_loop)      │      │   (_dispatch_loop)   │         │
│  │                     │      │                      │         │
│  │ - Fetch tasks       │      │ - Check capacity     │         │
│  │ - Add to queue      │      │ - Get next task      │         │
│  │ - Update stats      │      │ - Create execution   │         │
│  │ - Sleep 30s         │      │ - Track in pool      │         │
│  └──────┬──────────────┘      └──────┬───────────────┘         │
│         │                             │                          │
│         │                             │                          │
│         ▼                             ▼                          │
│  ┌─────────────────────────────────────────────────────┐        │
│  │              Shared State                            │        │
│  │  - TaskQueue (prioritized)                           │        │
│  │  - AgentPool (tracks active tasks)                   │        │
│  │  - ShutdownHandler (coordinates cleanup)             │        │
│  └─────────────────────────────────────────────────────┘        │
│                                                                   │
│  ┌────────────────────────────────────────────────────────┐     │
│  │ Shutdown Phase                                         │     │
│  │ - Wait for active tasks (up to shutdown_timeout)      │     │
│  │ - Mark orchestrator as stopped                         │     │
│  │ - Run cleanup callbacks                                │     │
│  └────────────────────────────────────────────────────────┘     │
└───────────────────────┬───────────────────────────────────────┬─┘
                        │                                       │
                        ▼                                       ▼
         ┌──────────────────────────┐        ┌────────────────────────┐
         │    TaskQueue             │        │    AgentPool           │
         │  - Priority queue        │        │  - Tracks active tasks │
         │  - Uses TaskPrioritizer  │        │  - Enforces max limit  │
         │  - Thread-safe (asyncio) │        │  - Manages lifecycle   │
         └────────┬─────────────────┘        └────────┬───────────────┘
                  │                                    │
                  ▼                                    ▼
         ┌──────────────────────────┐        ┌────────────────────────┐
         │   TaskPrioritizer        │        │   Task Execution       │
         │  - Multi-factor scoring  │        │  - subprocess.Popen    │
         │  - Due dates (10.0)      │        │  - Claude CLI          │
         │  - Dependencies (8.0)    │        │  - Output capture      │
         │  - User priority (7.0)   │        │  - Result posting      │
         │  - Project importance    │        │  - Database logging    │
         │  - Task age (3.0)        │        └────────────────────────┘
         └──────────────────────────┘
```

## Core Components

### 1. Orchestrator Class

**File**: `src/aegis/orchestrator/main.py:182`

The main coordination engine that manages the entire orchestration lifecycle.

**Responsibilities**:
- Initialize all subsystems (queue, pool, prioritizer, shutdown handler)
- Run dual event loops concurrently
- Coordinate clean shutdown
- Track system state in database

**Key Attributes**:
```python
class Orchestrator:
    settings: Settings              # Configuration
    asana_client: AsanaClient      # Asana API client
    prioritizer: TaskPrioritizer   # Task scoring engine
    task_queue: TaskQueue          # Priority queue
    agent_pool: AgentPool          # Concurrency manager
    shutdown_handler: ShutdownHandler  # Shutdown coordinator
    _running: bool                 # Orchestrator state flag
```

**Lifecycle**:
1. `__init__()` - Initialize components
2. `run()` - Start orchestration loops
3. Concurrent execution of `_poll_loop()` and `_dispatch_loop()`
4. Shutdown on signal or error
5. Cleanup and state persistence

### 2. TaskQueue Class

**File**: `src/aegis/orchestrator/main.py:37`

Priority queue for managing tasks awaiting execution.

**Design Pattern**: Priority queue with dynamic reprioritization

**Key Features**:
- Thread-safe using asyncio locks
- Tasks stored as dictionary (gid → AsanaTask)
- Priority calculated on-demand via TaskPrioritizer
- Non-destructive peek (task not removed until dispatched)

**Operations**:
```python
async def add_tasks(tasks: list[AsanaTask]) -> None
    # Add or update tasks in queue

async def remove_task(task_gid: str) -> None
    # Remove task after dispatching

async def get_next_task() -> tuple[AsanaTask, TaskScore] | None
    # Get highest priority task (non-destructive)

async def size() -> int
    # Current queue size
```

**Thread Safety**: All operations protected by asyncio.Lock

### 3. AgentPool Class

**File**: `src/aegis/orchestrator/main.py:112`

Manages bounded concurrency for task execution.

**Design Pattern**: Semaphore pattern with explicit tracking

**Key Features**:
- Configurable maximum concurrent tasks (default: 5)
- Tracks active asyncio.Task objects
- Provides capacity checking
- Supports graceful shutdown waiting

**Operations**:
```python
async def can_accept_task() -> bool
    # Check if pool has capacity

async def add_task(task_gid: str, task_coro: asyncio.Task) -> None
    # Add task to active pool

async def remove_task(task_gid: str) -> None
    # Remove completed task

async def wait_for_completion() -> None
    # Wait for all tasks to complete (shutdown)
```

**Capacity Management**:
- Max concurrent: Configurable via `max_concurrent_tasks` setting
- Backpressure: Dispatch loop waits when pool is full
- No queuing at pool level (TaskQueue handles queuing)

### 4. TaskPrioritizer

**File**: `src/aegis/orchestrator/prioritizer.py:71`

Intelligent multi-factor task scoring and ordering system.

**Scoring Factors** (configurable weights):

| Factor | Default Weight | Description |
|--------|----------------|-------------|
| Due Date | 10.0 | Urgency based on deadline proximity |
| Dependencies | 8.0 | Parent tasks prioritized over children |
| User Priority | 7.0 | Custom field values from Asana |
| Project Importance | 5.0 | Project-level priority configuration |
| Task Age | 3.0 | Anti-starvation for old tasks |

**Scoring Formula**:
```
total_score = (due_date_score × 10.0) +
              (dependency_score × 8.0) +
              (user_priority_score × 7.0) +
              (project_score × 5.0) +
              (age_score × 3.0)
```

**See**: `docs/PRIORITIZATION.md` for detailed scoring rules

### 5. ShutdownHandler

**File**: `src/aegis/utils/shutdown.py:22`

Coordinates graceful shutdown across all components.

**Key Features**:
- Signal handling (SIGTERM, SIGINT)
- Cooperative shutdown with timeout enforcement
- Resource tracking (tasks, subprocesses, sessions)
- Cleanup callback registry
- Configurable timeouts

**Shutdown Sequence**:
1. Catch signal → set shutdown flag
2. Stop accepting new work (loops check flag)
3. Wait for active tasks (up to `shutdown_timeout`)
4. Terminate subprocesses (SIGTERM → SIGKILL)
5. Close database sessions
6. Run cleanup callbacks
7. Restore signal handlers

**See**: `docs/SHUTDOWN_HANDLING.md` for detailed shutdown procedures

## Event Loop Architecture

### Main Event Loop: `Orchestrator.run()`

**File**: `src/aegis/orchestrator/main.py:215`

The main entry point that coordinates the entire system lifecycle.

```python
async def run(self) -> None:
    # 1. Initialize shutdown handler
    self.shutdown_handler = get_shutdown_handler(...)
    self.shutdown_handler.install_signal_handlers()

    # 2. Register cleanup callbacks
    self.shutdown_handler.register_cleanup_callback(mark_in_progress_tasks_interrupted_async)
    self.shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
    self.shutdown_handler.register_cleanup_callback(cleanup_db_connections)

    # 3. Mark orchestrator as running
    mark_orchestrator_running()
    self._running = True

    try:
        # 4. Start background tasks (concurrent execution)
        poll_task = asyncio.create_task(self._poll_loop())
        dispatch_task = asyncio.create_task(self._dispatch_loop())

        # 5. Wait for completion or shutdown
        done, pending = await asyncio.wait(
            [poll_task, dispatch_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # 6. Cancel remaining tasks
        for task in pending:
            task.cancel()
            await task  # Wait for cancellation

    except Exception as e:
        logger.error("orchestrator_error", error=str(e))
        raise
    finally:
        # 7. Graceful shutdown
        self._running = False
        await self.agent_pool.wait_for_completion()
        mark_orchestrator_stopped()
        await self.shutdown_handler.shutdown()
```

**Execution Model**: Two concurrent coroutines running in parallel

### Poll Loop: `_poll_loop()`

**File**: `src/aegis/orchestrator/main.py:279`

Background loop that discovers tasks from Asana and adds them to the queue.

**Pseudocode**:
```
WHILE orchestrator running AND NOT shutdown requested:
    TRY:
        # Fetch tasks from portfolio projects
        tasks ← fetch_tasks_from_portfolio()

        # Add to priority queue
        IF tasks NOT empty:
            task_queue.add_tasks(tasks)

            # Update system statistics
            update_system_stats(
                queue_size=queue.size(),
                active_count=pool.get_active_count()
            )

        # Update sync timestamp
        update_last_sync_time()

        LOG("poll_completed", tasks_found=count(tasks))

    CATCH Exception as e:
        LOG_ERROR("poll_loop_error", error=e)

    # Wait before next poll
    SLEEP(poll_interval_seconds)  # Default: 30s

LOG("poll_loop_stopped")
```

**Key Characteristics**:
- **Frequency**: Configurable via `poll_interval_seconds` (default: 30s)
- **Error Handling**: Exceptions logged but don't stop loop
- **Shutdown**: Checks `shutdown_requested` flag on each iteration
- **Idempotency**: Adding same task multiple times is safe (updates queue)

**Task Discovery**:
```python
async def _fetch_tasks_from_portfolio() -> list[AsanaTask]:
    # 1. Get all projects in configured portfolio
    projects = portfolios_api.get_items_for_portfolio(portfolio_gid)

    # 2. For each project, get incomplete unassigned tasks
    all_tasks = []
    for project in projects:
        tasks = asana_client.get_tasks_from_project(
            project.gid,
            assigned_only=False
        )
        # Filter: incomplete AND unassigned
        filtered = [t for t in tasks if not t.completed and not t.assignee]
        all_tasks.extend(filtered)

    return all_tasks
```

**Database Updates**:
- `system_state.last_tasks_sync_at` - Timestamp of last successful poll
- `system_state.total_tasks_pending` - Current queue size
- `system_state.active_agents_count` - Active task count

### Dispatch Loop: `_dispatch_loop()`

**File**: `src/aegis/orchestrator/main.py:323`

Background loop that dispatches tasks from queue to agents for execution.

**Pseudocode**:
```
WHILE orchestrator running AND NOT shutdown requested:
    TRY:
        # Check capacity
        IF NOT agent_pool.can_accept_task():
            SLEEP(1)
            CONTINUE

        # Get highest priority task
        next_task ← task_queue.get_next_task()
        IF next_task IS None:
            SLEEP(1)
            CONTINUE

        task, score ← next_task

        # Remove from queue (about to execute)
        task_queue.remove_task(task.gid)

        # Create execution coroutine
        execution_coro ← asyncio.create_task(_execute_task(task, score))

        # Add to agent pool
        agent_pool.add_task(task.gid, execution_coro)

        LOG("task_dispatched", task_gid=task.gid, priority_score=score.total_score)

    CATCH Exception as e:
        LOG_ERROR("dispatch_loop_error", error=e)

    # Small delay to prevent tight loop
    SLEEP(0.5)

LOG("dispatch_loop_stopped")
```

**Key Characteristics**:
- **Backpressure**: Waits when agent pool is full
- **Priority-Based**: Always dispatches highest priority task
- **Non-Blocking**: Short sleep when no work available
- **Error Isolation**: Dispatch errors don't affect other tasks
- **Shutdown**: Respects shutdown flag, stops accepting new tasks

**Flow Control**:
1. **Capacity Check**: Ensures pool isn't full
2. **Task Selection**: Gets highest priority task
3. **Queue Removal**: Task removed before execution starts
4. **Async Dispatch**: Task runs concurrently, doesn't block loop
5. **Pool Tracking**: Task added to active pool

### Task Execution: `_execute_task()`

**File**: `src/aegis/orchestrator/main.py:430`

Executes a single task using Claude CLI in a subprocess.

**Execution Flow**:
```
FUNCTION _execute_task(task: AsanaTask, score: TaskScore):
    session ← None
    execution_id ← None

    TRY:
        # 1. Create execution record
        session ← get_db()
        execution ← TaskExecution(
            task_id=None,  # TODO: Link to Task table
            status="in_progress",
            agent_type="claude_cli",
            started_at=now(),
            context={
                asana_task_gid: task.gid,
                asana_task_name: task.name,
                project_gids: [...]
            }
        )
        session.add(execution)
        session.commit()
        execution_id ← execution.id

        # 2. Get project code path
        code_path ← extract_code_path_from_project_notes(task.projects[0])

        # 3. Format task context
        task_context ← format_task_for_claude(task, code_path)

        # 4. Execute Claude CLI
        process ← subprocess.Popen(
            ["claude", "--dangerously-skip-permissions", task_context],
            cwd=code_path,
            stdout=PIPE,
            stderr=PIPE,
            text=True
        )

        # Track subprocess for shutdown handling
        shutdown_handler.track_subprocess(process)

        TRY:
            # Wait for completion (5 minute timeout)
            stdout, stderr ← process.communicate(timeout=300)
        FINALLY:
            shutdown_handler.untrack_subprocess(process)

        output ← stdout + stderr

        # 5. Update execution record
        execution.status ← "completed" IF returncode == 0 ELSE "failed"
        execution.completed_at ← now()
        execution.success ← returncode == 0
        execution.output ← output[:50000]  # Truncate if needed
        execution.duration_seconds ← calculate_duration()

        IF returncode != 0:
            execution.error_message ← f"Exit code: {returncode}"

        session.commit()

        # 6. Post result to Asana
        status_emoji ← "✓" IF success ELSE "⚠️"
        comment ← format_completion_comment(execution, score, output)
        asana_client.add_comment(task.gid, comment)

        LOG("task_execution_completed", success=execution.success)

    CATCH Exception as e:
        LOG_ERROR("task_execution_failed", error=e)

        # Update execution record
        IF execution_id:
            execution.status ← "failed"
            execution.error_message ← str(e)
            session.commit()

        # Post error to Asana
        error_comment ← format_error_comment(e)
        asana_client.add_comment(task.gid, error_comment)

    FINALLY:
        # Remove from agent pool
        agent_pool.remove_task(task.gid)

        # Close database session
        IF session:
            session.close()
```

**Key Features**:
- **Database Tracking**: Full execution lifecycle logged to `task_executions` table
- **Subprocess Management**: Tracked for graceful shutdown
- **Timeout Enforcement**: 5-minute limit per task
- **Result Posting**: Success/failure posted back to Asana
- **Error Isolation**: Failures don't affect other tasks
- **Resource Cleanup**: Always removes task from pool

**Context Format**:
```
Task: {task.name}

Project: {project.name}
Code Location: {code_path}

Task Description:
{task.notes}
```

## Sequence Diagrams

### Normal Operation Flow

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐
│  Asana   │  │PollLoop  │  │TaskQueue │  │Dispatch  │  │ AgentPool │
│          │  │          │  │          │  │  Loop    │  │           │
└────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘
     │             │              │             │              │
     │◄────────────┤              │             │              │
     │ GET /portfolio/tasks       │             │              │
     ├────────────►│              │             │              │
     │  tasks[]    │              │             │              │
     │             ├─────────────►│             │              │
     │             │ add_tasks()  │             │              │
     │             │              ├─────────────┤              │
     │             │              │   success   │              │
     │             │              │             │              │
     │             │              │◄────────────┤              │
     │             │              │get_next()   │              │
     │             │              ├────────────►│              │
     │             │              │(task,score) │              │
     │             │              │             │              │
     │             │              │             ├─────────────►│
     │             │              │             │can_accept?   │
     │             │              │             │◄─────────────┤
     │             │              │             │   true       │
     │             │              │             │              │
     │             │              │◄────────────┤              │
     │             │              │remove_task()│              │
     │             │              ├────────────►│              │
     │             │              │             │              │
     │             │              │             ├─────────────►│
     │             │              │             │ add_task()   │
     │             │              │             │  (execute)   │
     │             │              │             │              │
     ┌─────────────────────────────────────────────────────────┴────┐
     │                    Task Execution                             │
     │  1. Create TaskExecution record                               │
     │  2. Launch Claude CLI subprocess                              │
     │  3. Wait for completion (timeout: 5min)                       │
     │  4. Update TaskExecution with results                         │
     │  5. Post comment to Asana                                     │
     └───────────────────────────────────────────────────────────────┘
     │             │              │             │              │
     │◄────────────┼──────────────┼─────────────┤              │
     │ POST /tasks/{gid}/comments │             │              │
     ├────────────►│              │             │              │
     │   created   │              │             │              │
     │             │              │             │◄─────────────┤
     │             │              │             │remove_task() │
     │             │              │             ├─────────────►│
     │             │              │             │              │
```

### Shutdown Sequence

```
┌────────┐  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐
│ SIGINT │  │Shutdown │  │PollLoop  │  │Dispatch  │  │ AgentPool │
│        │  │ Handler │  │          │  │  Loop    │  │           │
└───┬────┘  └────┬────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘
    │            │             │             │              │
    ├───────────►│             │             │              │
    │ SIGINT     │             │             │              │
    │            ├─────────────┼─────────────┼─────────────►│
    │            │ set shutdown_requested = True            │
    │            │             │             │              │
    │            │             ├─────────────┤              │
    │            │             │check flag   │              │
    │            │             ├────────────►│              │
    │            │             │ STOP        │              │
    │            │             │             │              │
    │            │             │             ├─────────────►│
    │            │             │             │check flag    │
    │            │             │             ├─────────────►│
    │            │             │             │   STOP       │
    │            │             │             │              │
    │            │◄────────────┼─────────────┼──────────────┤
    │            │       wait_for_completion()              │
    │            ├─────────────────────────────────────────►│
    │            │                                           │
    │            │  ┌─────────────────────────────────┐     │
    │            │  │ Wait for active tasks           │     │
    │            │  │ Timeout: shutdown_timeout (300s)│     │
    │            │  └─────────────────────────────────┘     │
    │            │                                           │
    │            │◄──────────────────────────────────────────┤
    │            │             completed                     │
    │            │                                           │
    │            ├─────────────┐                             │
    │            │ terminate_subprocesses()                  │
    │            ├────────────►│                             │
    │            │ SIGTERM → wait → SIGKILL                  │
    │            │                                           │
    │            ├─────────────┐                             │
    │            │ close_database_sessions()                 │
    │            ├────────────►│                             │
    │            │                                           │
    │            ├─────────────┐                             │
    │            │ run_cleanup_callbacks()                   │
    │            ├────────────►│                             │
    │            │ - mark_in_progress_tasks_interrupted()    │
    │            │ - mark_orchestrator_stopped()             │
    │            │ - cleanup_db_connections()                │
    │            │                                           │
    │            ├─────────────┐                             │
    │            │ restore_signal_handlers()                 │
    │            ├────────────►│                             │
    │◄───────────┤                                           │
│   EXIT 130   │                                           │
```

### Error Handling Flow

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────┐
│PollLoop  │  │Dispatch  │  │  Task    │  │  Asana    │
│          │  │  Loop    │  │Execution │  │           │
└────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬─────┘
     │             │              │              │
     ├─────────────┐              │              │
     │ Fetch Error │              │              │
     ├────────────►│              │              │
     │ LOG ERROR   │              │              │
     │ CONTINUE    │              │              │
     ├─────────────┘              │              │
     │             │              │              │
     │             ├─────────────►│              │
     │             │ execute()    │              │
     │             │              ├──────────────┐
     │             │              │Process fails │
     │             │              │exit code: 1  │
     │             │              ├─────────────►│
     │             │              │              │
     │             │  ┌──────────────────────────┤
     │             │  │ 1. Log to database       │
     │             │  │    status='failed'       │
     │             │  │    error_message='...'   │
     │             │  │                          │
     │             │  │ 2. Post error to Asana   │
     │             │  └──────────────────────────┤
     │             │              │              │
     │             │              │◄─────────────┤
     │             │              │  comment_gid │
     │             │◄─────────────┤              │
     │             │ remove_task()│              │
     │             ├─────────────►│              │
     │             │              │              │
     │             │ ┌────────────┘              │
     │             │ │ Task removed from pool    │
     │             │ │ Other tasks continue      │
     │             │ │ No cascade failure        │
     │             │ └────────────┐              │
     │             │              │              │
```

## Error Handling & Recovery

### Error Categories

| Category | Scope | Handling Strategy | Recovery |
|----------|-------|-------------------|----------|
| **Poll Errors** | Asana API failures | Log error, continue loop | Retry on next poll (30s) |
| **Dispatch Errors** | Queue/pool failures | Log error, continue loop | Task remains in queue |
| **Execution Errors** | Task processing failures | Log to database, post to Asana | Task marked failed, can be retried manually |
| **Subprocess Errors** | Claude CLI failures | Capture output, log error | Post error to Asana for user review |
| **Database Errors** | Connection/query failures | Log error, attempt session recovery | Create new session on next operation |
| **Shutdown Errors** | Cleanup failures | Log error, continue shutdown | Best-effort cleanup, force if needed |

### Error Isolation

**Key Principle**: Errors in one component don't cascade to others.

**Isolation Mechanisms**:
1. **Try-Catch per Loop Iteration**: Each poll/dispatch cycle isolated
2. **Per-Task Error Handling**: Task failures don't affect other tasks
3. **Subprocess Tracking**: Process crashes handled independently
4. **Database Session Isolation**: Each execution gets its own session

**Example - Task Execution Error Isolation**:
```python
async def _execute_task(task: AsanaTask, score: TaskScore) -> None:
    try:
        # Task execution logic
        ...
    except Exception as e:
        # Log error
        logger.error("task_execution_failed", error=str(e))

        # Update database (if possible)
        try:
            mark_execution_failed(execution_id, error=str(e))
        except:
            pass  # Don't let database error prevent Asana notification

        # Notify user via Asana (if possible)
        try:
            post_error_to_asana(task.gid, error=str(e))
        except:
            pass  # Best effort
    finally:
        # ALWAYS clean up
        agent_pool.remove_task(task.gid)
        if session:
            session.close()
```

### Retry Strategy

**Current Implementation**: No automatic retries (user-initiated only)

**Rationale**:
- Many failures require user input (clarification, bug fixes)
- Automatic retries could waste API credits
- Users can manually reassign failed tasks in Asana

**Future Enhancement** (Phase 2+):
- Configurable retry policy per task type
- Exponential backoff for transient failures
- Automatic retry for specific error categories (network, rate limits)

### Recovery Mechanisms

| Failure Type | Detection | Recovery Action |
|--------------|-----------|-----------------|
| **Lost Connection** | API call exception | Wait for next poll cycle, attempt reconnect |
| **Database Unavailable** | SQLAlchemy exception | Log error, continue with in-memory state, attempt reconnect |
| **Process Hang** | Subprocess timeout | SIGTERM → wait → SIGKILL |
| **Queue Corruption** | Internal state error | Clear queue, repopulate from Asana on next poll |
| **Pool Overflow** | Assertion error | Wait for tasks to complete, reject new dispatches |

### Observability

**Structured Logging** (JSON format):
```python
logger.info("task_execution_started",
    task_gid="123456",
    task_name="Build authentication",
    execution_id=789,
    priority_score=87.5
)

logger.error("task_execution_failed",
    task_gid="123456",
    execution_id=789,
    error="Subprocess exited with code 1",
    duration_seconds=45,
    exc_info=True
)
```

**Database Auditing**:
- All executions logged to `task_executions` table
- Agent lifecycle tracked in `agents` table
- Detailed events in `agent_events` table
- System metrics in `system_state` table

**Health Monitoring**:
```python
# System state tracked in database
system_state:
    orchestrator_status: "running" | "stopped" | "paused"
    orchestrator_pid: process ID
    orchestrator_started_at: timestamp
    total_tasks_pending: queue size
    active_agents_count: current concurrency
    last_tasks_sync_at: last successful poll
```

## Multi-Task Concurrency

### Concurrency Model

**Pattern**: Bounded parallelism with cooperative scheduling

**Characteristics**:
- **Bounded**: Maximum `max_concurrent_tasks` (default: 5) tasks running simultaneously
- **Cooperative**: Tasks don't preempt each other; scheduler based on priority
- **Async**: I/O-bound operations (Asana API, database) use async/await
- **Isolated**: Tasks run in separate subprocesses (Claude CLI)

### Concurrency Control

**AgentPool Semaphore Pattern**:
```python
class AgentPool:
    def __init__(self, max_concurrent: int):
        self.max_concurrent = max_concurrent
        self._active_tasks: dict[str, asyncio.Task] = {}

    async def can_accept_task(self) -> bool:
        async with self._lock:
            return len(self._active_tasks) < self.max_concurrent

    async def add_task(self, task_gid: str, task_coro: asyncio.Task):
        async with self._lock:
            self._active_tasks[task_gid] = task_coro
```

**Backpressure Handling**:
```python
# Dispatch loop waits when pool is full
while running:
    if not await agent_pool.can_accept_task():
        await asyncio.sleep(1)  # Wait for capacity
        continue

    # Proceed with dispatch
    ...
```

### Resource Management

**CPU/Memory**:
- Each task runs in separate subprocess (Claude CLI)
- Memory isolated per process
- CPU shared via OS scheduler
- No explicit CPU limits (rely on OS)

**I/O**:
- Asana API: Rate limits handled by client library
- Database: Connection pool managed by SQLAlchemy
- File system: Reads/writes in subprocess (isolated)

**Scaling Considerations**:
- **Scale Up**: Increase `max_concurrent_tasks` (test for resource limits)
- **Scale Out**: Run multiple orchestrator instances (future Phase 4)
- **Bottlenecks**: Asana API rate limits, database connection pool

### Dependency Handling

**Current**: Basic parent-child awareness via prioritization

**Priority Boost**:
- Parent tasks (with subtasks) get higher dependency score (8.0)
- Child tasks get lower score (3.0)
- Naturally processes parents before children

**Future Enhancement** (Phase 2):
- Explicit dependency graph
- Block child execution until parent completes
- Parallel execution of independent subtasks

## Configuration

### Environment Variables

**Orchestration Settings**:
```bash
# Polling configuration
POLL_INTERVAL_SECONDS=30              # How often to check Asana

# Concurrency configuration
MAX_CONCURRENT_TASKS=5                 # Maximum parallel tasks

# Shutdown configuration
SHUTDOWN_TIMEOUT=300                   # Max wait for tasks (seconds)
SUBPROCESS_TERM_TIMEOUT=10             # SIGTERM wait before SIGKILL

# Task prioritization weights
PRIORITY_WEIGHT_DUE_DATE=10.0
PRIORITY_WEIGHT_DEPENDENCY=8.0
PRIORITY_WEIGHT_USER_PRIORITY=7.0
PRIORITY_WEIGHT_PROJECT_IMPORTANCE=5.0
PRIORITY_WEIGHT_AGE=3.0
```

**Code Reference**: `src/aegis/config.py:44`

### Runtime Configuration

**Accessing Settings**:
```python
from aegis.config import get_settings

settings = get_settings()
orchestrator = Orchestrator(settings)
```

**Dynamic Updates**:
- Settings loaded at startup from environment
- Changes require orchestrator restart
- Future: Hot reload configuration (Phase 3+)

## Performance Characteristics

### Throughput

**Polling Overhead**:
- Poll frequency: 30 seconds
- API calls per poll: 1 (portfolio) + N (projects)
- Average poll time: ~2-5 seconds (depends on project count)

**Task Execution**:
- Average task duration: Varies (1-10 minutes typical)
- Max concurrent tasks: 5 (default)
- Theoretical max throughput: ~0.5-5 tasks/minute (depends on task complexity)

**Bottlenecks**:
1. Task execution time (subprocess duration)
2. Asana API rate limits (~150 requests/minute)
3. Database connection pool (default: 10 connections)

### Latency

**Task Discovery Latency**: 0-30 seconds (polling interval)

**Dispatch Latency**: Near-instant (<1 second) once in queue

**End-to-End Latency**:
```
Task created in Asana
  → [0-30s] Discovered by poll loop
  → [<1s] Added to queue and prioritized
  → [0-60s] Wait for agent pool capacity
  → [1-10min] Task execution
  → [<1s] Result posted to Asana
```

### Resource Usage

**Memory**:
- Orchestrator base: ~50-100 MB
- Per-task overhead: ~200-500 MB (subprocess)
- Database connections: ~5-10 MB each
- Total (5 concurrent tasks): ~1.5-3 GB

**CPU**:
- Orchestrator loops: <1% (mostly sleeping)
- Task execution: Varies (subprocess workload)
- Typical: 10-50% per active task

**Network**:
- Asana API: ~10-50 KB per request
- Poll frequency: ~1-5 requests/30s
- Bandwidth: <1 Mbps typical

## Deployment Considerations

### Running the Orchestrator

**Development**:
```bash
# Direct execution
aegis orchestrate

# With custom settings
export MAX_CONCURRENT_TASKS=10
aegis orchestrate
```

**Production** (Phase 4):
- Run as systemd service
- Auto-restart on failure
- Log rotation configured
- Health check endpoint

### Monitoring

**Key Metrics to Track**:
- `orchestrator_status` - Running/stopped state
- `total_tasks_pending` - Queue size
- `active_agents_count` - Current concurrency
- `tasks_completed` - Success rate
- `tasks_failed` - Error rate
- `avg_task_duration` - Performance trend

**Alerting** (Future):
- Orchestrator stopped unexpectedly
- Queue size exceeds threshold
- Error rate above normal
- Task duration anomalies

### Database Maintenance

**Cleanup Recommendations**:
- Archive old `task_executions` (>90 days)
- Prune `agent_events` (>30 days)
- Vacuum database weekly
- Monitor connection pool usage

## Future Enhancements

### Phase 2: Advanced Orchestration

1. **Webhook Support**
   - Replace polling with real-time webhooks
   - Reduce latency to <1 second
   - Lower API usage

2. **Advanced Dependency Management**
   - Explicit dependency graph
   - Parallel execution of independent subtasks
   - Blocked task handling

3. **Dynamic Scaling**
   - Auto-adjust `max_concurrent_tasks` based on load
   - CPU/memory-aware scaling
   - Graceful scale-down

4. **Retry Policies**
   - Configurable per-task retry logic
   - Exponential backoff
   - Circuit breaker for failing tasks

### Phase 3: Intelligence

1. **Predictive Prioritization**
   - Machine learning for task duration estimation
   - Historical success rate influence
   - User pattern learning

2. **Adaptive Scheduling**
   - Time-of-day awareness
   - User availability correlation
   - Resource optimization

3. **Smart Recovery**
   - Automatic checkpoint/resume
   - Partial work preservation
   - Intelligent retry decisions

### Phase 4: Scale

1. **Distributed Orchestration**
   - Multiple orchestrator instances
   - Redis-based coordination
   - Distributed queue

2. **Multi-Tenancy**
   - Per-workspace orchestrators
   - Resource isolation
   - Fair scheduling across tenants

3. **Advanced Observability**
   - Real-time dashboard
   - Distributed tracing
   - Performance analytics

## Testing Strategy

### Unit Tests

**Target**: Individual components in isolation

**Coverage**:
- `TaskQueue` operations (add, remove, prioritize)
- `AgentPool` capacity management
- `TaskPrioritizer` scoring logic
- `ShutdownHandler` lifecycle

**Location**: `tests/unit/`

### Integration Tests

**Target**: Component interactions

**Scenarios**:
- Poll → Queue → Dispatch → Execute flow
- Error propagation and recovery
- Shutdown with active tasks
- Database state consistency

**Location**: `tests/integration/`

### End-to-End Tests

**Target**: Full system behavior

**Scenarios**:
- Create task in Asana → Auto-execution → Result posted
- Multiple concurrent tasks
- Graceful shutdown during execution
- Recovery from orchestrator restart

**Location**: `tests/integration/test_e2e.py`

**See**: `tests/integration/E2E_TEST_GUIDE.md`

## References

### Implementation Files

- **Main Orchestrator**: `src/aegis/orchestrator/main.py:182`
- **Task Queue**: `src/aegis/orchestrator/main.py:37`
- **Agent Pool**: `src/aegis/orchestrator/main.py:112`
- **Task Prioritizer**: `src/aegis/orchestrator/prioritizer.py:71`
- **Shutdown Handler**: `src/aegis/utils/shutdown.py:22`
- **Configuration**: `src/aegis/config.py:44`
- **Database Models**: `src/aegis/database/models.py`

### Documentation

- **Project Overview**: `design/PROJECT_OVERVIEW.md`
- **Task Prioritization**: `docs/PRIORITIZATION.md`
- **Shutdown Handling**: `docs/SHUTDOWN_HANDLING.md`
- **Database Schema**: `design/DATABASE_SCHEMA.md`

### Related Design Documents

- **Autonomous Work Pattern**: `design/AUTONOMOUS_WORK_PATTERN.md`
- **Task List & Roadmap**: `design/TASK_LIST.md`

## Appendix: Design Rationale

### Why Polling vs Webhooks?

**Decision**: Start with polling, add webhooks in Phase 2+

**Rationale**:
1. **Simplicity**: Polling requires only read API access, no webhook infrastructure
2. **Debuggability**: Easy to pause, inspect, and resume
3. **Reliability**: No webhook delivery failures or missed events
4. **Development Speed**: Faster to implement and iterate

**Trade-offs**:
- Latency: 0-30s vs near-instant
- API Usage: More requests vs fewer
- Future work: Will add webhooks as enhancement

### Why asyncio vs Threading?

**Decision**: asyncio-based architecture

**Rationale**:
1. **I/O Bound**: Most operations (API calls, database) are I/O-bound
2. **Async/Await**: Clean, readable concurrency model
3. **Native Support**: Modern Python libraries support async
4. **Resource Efficiency**: Lower overhead than threads

**Trade-offs**:
- Learning curve for async patterns
- Some libraries still synchronous (wrapped with `asyncio.to_thread`)

### Why In-Memory Queue vs Persistent Queue?

**Decision**: In-memory priority queue with database as source of truth

**Rationale**:
1. **Performance**: Fast prioritization without database queries
2. **Simplicity**: No external queue service (Redis, RabbitMQ)
3. **Stateless**: Queue rebuilt on restart from Asana/database
4. **Flexibility**: Easy to reprioritize dynamically

**Trade-offs**:
- Queue lost on restart (acceptable - rebuilt in 30s)
- Not distributed (single orchestrator) - addressed in Phase 4

### Why Bounded Concurrency vs Unlimited?

**Decision**: Configurable max concurrent tasks (default: 5)

**Rationale**:
1. **Resource Control**: Prevent memory/CPU exhaustion
2. **Quality of Service**: Maintain responsiveness
3. **Cost Management**: Limit Claude API usage
4. **Predictability**: Easier capacity planning

**Trade-offs**:
- Lower throughput than unlimited
- May need tuning per deployment

## Approval & Sign-Off

**Document Version**: 1.0
**Created**: 2025-11-25
**Status**: ✅ **READY FOR REVIEW**

**Author**: Claude (Orchestration Design)
**Reviewer**: [Pending]

**Acceptance Criteria**:
- [x] Clear architecture documented
- [x] Sequence diagrams for main flows
- [x] Error handling strategy defined
- [x] Shutdown mechanism specified
- [x] Concurrency model explained
- [x] Configuration documented
- [x] Performance characteristics described
- [x] Future enhancements outlined

**Next Steps**:
1. Review design document
2. Validate against requirements
3. Identify gaps or concerns
4. Approve for implementation
5. Use as reference during development
