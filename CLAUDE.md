# CLAUDE.md - AI Assistant Guide for Aegis Development

**Last Updated**: 2025-11-28

This document provides comprehensive guidance for AI assistants (like Claude) working on the Aegis codebase. It covers architecture, development workflows, testing procedures, and common patterns.

> 📚 **Looking for detailed file documentation?** See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for a complete file-by-file map of the codebase with line counts, purposes, and relationships.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Codebase Structure](#codebase-structure)
4. [Key Modules](#key-modules)
5. [Development Workflow](#development-workflow)
6. [Testing Guidelines](#testing-guidelines)
7. [Common Patterns](#common-patterns)
8. [Important Conventions](#important-conventions)
9. [Troubleshooting](#troubleshooting)

---

## Project Overview

**Aegis** is an intelligent assistant orchestration system that uses **Asana as the control plane**. Instead of building another chat interface, Aegis leverages Asana's familiar project management UI to coordinate complex, multi-step tasks through specialized AI agents.

### Core Concept
- Users create tasks in Asana and assign them to Aegis
- Aegis fetches tasks, executes them using Claude Code, and reports back
- Results are posted as comments, tasks are moved to "Implemented" section
- Autonomous mode (`aegis work-on`) can process multiple tasks automatically

### Current Status
🏗️ **Alpha** - MVP functionality complete with autonomous execution capability

### Key Technologies
- **Language**: Python 3.11+
- **LLM**: Claude (Anthropic API via Claude Code CLI)
- **Interface**: Asana API (Python SDK)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **CLI**: Click framework
- **Testing**: pytest with pytest-asyncio
- **Logging**: structlog

---

## Architecture

### System Components

```
┌─────────────────────────────────────────────────────────┐
│                       ASANA                             │
│  (Projects, Tasks, Comments, Sections, Dependencies)   │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│                   AEGIS CLI                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐             │
│  │   do     │  │ work-on  │  │ organize │             │
│  └──────────┘  └──────────┘  └──────────┘             │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              ASANA CLIENT (API Wrapper)                 │
│  - Fetch tasks from projects                            │
│  - Post comments                                         │
│  - Update task status                                    │
│  - Move tasks to sections                                │
│  - Manage dependencies                                   │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│                  CLAUDE CODE CLI                        │
│  - Execute tasks with full AI capabilities              │
│  - Read/write files, run commands                        │
│  - Return results via stdout                             │
└────────┬────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────┐
│              POSTGRESQL DATABASE                        │
│  - Task execution history                                │
│  - System state tracking                                 │
│  - Comments log                                          │
│  - Orchestrator status                                   │
└─────────────────────────────────────────────────────────┘
```

### Data Flow: Autonomous Execution

1. **Discovery**: `aegis work-on` fetches all tasks from Asana project
2. **Assessment**: Checks for blockers (missing dependencies, environment issues)
3. **Question Creation**: Creates question tasks in Asana for any blockers
4. **Execution**: Runs ready tasks through Claude Code subprocess
5. **Reporting**: Posts results as comments, marks tasks complete
6. **Completion**: Moves completed tasks to "Implemented" section

---

## Codebase Structure

```
aegis/
├── .env                        # Environment configuration (secrets)
├── .env.example                # Template for environment variables
├── pyproject.toml              # Python package configuration
├── alembic.ini                 # Database migrations config
├── docker-compose.yml          # Local services (PostgreSQL, Redis)
│
├── src/aegis/                  # Source code
│   ├── __init__.py
│   ├── config.py               # Settings management (Pydantic)
│   ├── cli.py                  # CLI commands (Click) [MAIN FILE - 950 lines]
│   │
│   ├── asana/                  # Asana API integration
│   │   ├── client.py           # AsanaClient wrapper [530 lines]
│   │   └── models.py           # Pydantic models for Asana entities
│   │
│   ├── database/               # Database layer
│   │   ├── models.py           # SQLAlchemy ORM models
│   │   ├── session.py          # Database session management
│   │   └── state.py            # System state tracking functions
│   │
│   ├── orchestrator/           # Task orchestration
│   │   ├── main.py             # Main orchestrator loop (future)
│   │   └── prioritizer.py      # Task prioritization algorithm [387 lines]
│   │
│   ├── utils/                  # Utilities
│   │   └── shutdown.py         # Graceful shutdown handler [376 lines]
│   │
│   └── agents/                 # Agent implementations (future)
│
├── tests/                      # Test suite
│   ├── unit/                   # Unit tests
│   │   ├── test_prioritizer.py # 36 tests, 92% coverage
│   │   └── test_shutdown.py    # 29 tests, 91% coverage
│   │
│   └── integration/            # Integration tests
│       ├── test_e2e.py         # 14 E2E tests
│       ├── E2E_TEST_GUIDE.md   # Complete testing guide
│       └── TEST_SUMMARY.md     # Test overview
│
├── docs/                       # Documentation
│   ├── OPERATOR_GUIDE.md       # For operators/users
│   ├── SHUTDOWN_HANDLING.md    # Shutdown implementation docs
│   └── PRIORITIZATION.md       # Task prioritization docs
│
├── design/                     # Design documents
│   ├── PROJECT_OVERVIEW.md     # Project vision and architecture
│   ├── TASK_LIST.md            # Detailed roadmap
│   ├── DATABASE_SCHEMA.md      # Database design
│   └── ORCHESTRATION.md        # Orchestration architecture
│
├── logs/                       # Execution logs
│   └── aegis.log               # Main log file (appended by each run)
│
├── alembic/                    # Database migrations
│   └── versions/               # Migration scripts
│
└── scripts/                    # Utility scripts
    └── setup_test_env.sh       # Test environment setup
```

---

## Key Modules

### 1. CLI (`src/aegis/cli.py`) - 950 lines

**Purpose**: Main entry point for all Aegis commands

**Key Commands**:
- `aegis config` - Display current configuration
- `aegis test-asana` - Test Asana API connection
- `aegis test-claude` - Test Claude API connection
- `aegis do <task_or_project>` - Execute a specific task or first available task from project
- `aegis work-on <project>` - Autonomous multi-task execution
- `aegis start <project>` - Start orchestrator for continuous task monitoring
- `aegis organize <task_or_project>` - Apply section structure template to project(s)
- `aegis plan <task_or_project>` - Review tasks and ensure target number in "Ready to Implement"
- `aegis sync` - Sync Asana projects and tasks into local database
- `aegis create-agents-project` - Create the Agents project in the portfolio
- `aegis process-agent-mentions <project>` - Monitor project for @-mentions of agents and respond

**Important Functions**:
```python
# Lines 118-362: do command - single task execution
@main.command()
def do(project_name: str, terminal: bool) -> None

# Lines 387-934: work_on command - autonomous execution
@main.command()
def work_on(project_name: str, max_tasks: int, dry_run: bool, terminal: bool) -> None

# Lines 791-879: organize command - project structure setup
@main.command()
def organize(project_name: str) -> None

# Lines 25-81: launch_in_hyper_terminal - terminal mode support
def launch_in_hyper_terminal(command: list[str], cwd: str | None = None) -> int
```

**Recent Changes**:
- ✅ Added automatic task completion and section movement (lines 908-921)
- ✅ Fixed dependency API signature (line 777)
- ✅ Added terminal mode support (lines 25-81, integrated at 349-361 and 814-833)

---

### 2. Asana Client (`src/aegis/asana/client.py`) - 530 lines

**Purpose**: Wrapper around Asana Python SDK with async support and retry logic

**Key Methods**:
```python
class AsanaClient:
    # Task operations
    async def get_tasks_from_project(project_gid, assigned_only=False) -> list[AsanaTask]
    async def get_task(task_gid) -> AsanaTask
    async def update_task(task_gid, updates: AsanaTaskUpdate) -> AsanaTask

    # Comment operations
    async def add_comment(task_gid, text) -> AsanaComment
    async def get_comments(task_gid) -> list[AsanaComment]

    # Project operations
    async def get_project(project_gid) -> AsanaProject
    async def get_sections(project_gid) -> list[AsanaSection]
    async def create_section(project_gid, section_name) -> AsanaSection
    async def move_task_to_section(task_gid, project_gid, section_gid) -> None

    # Utility operations
    async def ensure_project_sections(project_gid, section_names) -> dict[str, str]
    async def complete_task_and_move_to_implemented(task_gid, project_gid) -> AsanaTask
```

**Features**:
- Automatic retry with exponential backoff (3 attempts)
- Converts synchronous Asana SDK calls to async using `asyncio.to_thread`
- Structured logging with structlog
- All API calls use `opts` dict format for consistency

**API Call Pattern**:
```python
# Correct pattern used throughout:
await asyncio.to_thread(
    self.api.method_name,
    required_arg,
    {"opt_fields": "field1,field2", "body": {"data": {...}}}
)
```

---

### 3. Configuration (`src/aegis/config.py`) - 130 lines

**Purpose**: Environment variable management using Pydantic Settings

**Settings Class**:
```python
class Settings(BaseSettings):
    # Asana
    asana_access_token: str
    asana_workspace_gid: str
    asana_portfolio_gid: str

    # Anthropic
    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    # Database
    database_url: str = "postgresql://localhost/aegis"
    redis_url: str = "redis://localhost:6379"

    # Orchestrator
    poll_interval_seconds: int = 30
    max_concurrent_tasks: int = 5

    # Task Prioritization (5 weighted factors)
    priority_weight_due_date: float = 10.0
    priority_weight_dependencies: float = 8.0
    priority_weight_user_priority: float = 7.0
    priority_weight_project: float = 5.0
    priority_weight_age: float = 3.0
```

**Usage**:
```python
from aegis.config import Settings
config = Settings()  # Loads from .env file
```

---

### 4. Database Models (`src/aegis/database/models.py`) - 330 lines

**Purpose**: SQLAlchemy ORM models for data persistence

**Models**:
```python
# System state tracking
class SystemState(Base):
    orchestrator_pid: int | None
    orchestrator_status: str  # "running" | "stopped"

# Task execution tracking
class TaskExecution(Base):
    task_id: str  # Asana GID
    project_id: str
    status: str  # "pending" | "in_progress" | "completed" | "failed"
    started_at: datetime | None
    completed_at: datetime | None
    result: str | None
    error_message: str | None
    execution_metadata: dict | None  # Changed from 'metadata' to avoid SQLAlchemy conflict

# Comment logging
class CommentLog(Base):
    task_id: str
    comment_id: str
    comment_text: str
    posted_at: datetime
```

**Database Operations**:
- All operations use async session management
- Transactions managed via `async with get_async_session()`
- Cleanup handled by shutdown callbacks

---

### 5. Task Prioritizer (`src/aegis/orchestrator/prioritizer.py`) - 387 lines

**Purpose**: Multi-factor task prioritization algorithm

**Scoring Factors** (weighted):
1. **Due Date Urgency** (weight 10.0) - Overdue tasks get highest priority
2. **Dependencies** (weight 8.0) - Parent tasks prioritized over children
3. **User Priority** (weight 7.0) - Custom field from Asana
4. **Project Importance** (weight 5.0) - Critical projects boosted
5. **Age** (weight 3.0) - Older tasks gradually increase priority

**Usage**:
```python
from aegis.orchestrator.prioritizer import TaskPrioritizer, PriorityConfig

config = PriorityConfig()  # Uses settings from environment
prioritizer = TaskPrioritizer(config)

sorted_tasks = await prioritizer.prioritize_tasks(tasks, projects_by_gid)
# Returns tasks sorted by priority score (highest first)
```

**Tests**: 36 unit tests, 92% coverage

---

### 6. Graceful Shutdown (`src/aegis/utils/shutdown.py`) - 376 lines

**Purpose**: Handles SIGTERM/SIGINT signals and coordinates graceful shutdown

**Features**:
- Signal handler installation (SIGTERM, SIGINT)
- Task tracking with configurable timeout
- Subprocess management (SIGTERM → wait → SIGKILL)
- Cleanup callbacks with async support
- Database state persistence
- Resource cleanup (sessions, connections)

**Usage**:
```python
from aegis.utils.shutdown import get_shutdown_handler

shutdown_handler = get_shutdown_handler(shutdown_timeout=300)
shutdown_handler.install_signal_handlers()

# Register cleanup callbacks
shutdown_handler.register_cleanup_callback(cleanup_function)

# Check in main loop
while not shutdown_handler.shutdown_requested:
    await process_tasks()

# Always cleanup
try:
    await run_application()
finally:
    await shutdown_handler.shutdown()
```

**Tests**: 29 unit tests, 91% coverage

### 7. Orchestrator (`src/aegis/orchestrator/main.py`) - 983 lines

**Purpose**: Continuous task monitoring and execution engine

**Features**:
- **Task Queue**: Priority-based queue using TaskPrioritizer
- **Agent Pool**: Concurrent execution management (configurable max concurrency)
- **Polling Loop**: Fetches new tasks at configurable intervals (default: 30s)
- **Dispatch Loop**: Assigns tasks from queue to available agents
- **Live Display**: Full-screen rich console display with real-time updates
- **Web Dashboard**: FastAPI-based web interface (default port: 8000)
- **Execution Modes**:
  - `simple_executor`: Uses SimpleExecutor agent via `aegis do` subprocess
  - `claude_cli`: Direct Claude CLI subprocess (legacy)
- **Graceful Shutdown**: Waits for active tasks or terminates on signal

**Usage**:
```bash
# Start orchestrator for a project
aegis start Aegis

# With environment variables
POLL_INTERVAL_SECONDS=60 MAX_CONCURRENT_TASKS=5 aegis start Aegis
```

**How It Works**:
1. **Initialization**: Sets up task queue, agent pool, prioritizer, and display
2. **Polling**: Fetches incomplete, unassigned tasks from Asana project every N seconds
3. **Prioritization**: Scores tasks using multi-factor algorithm
4. **Dispatch**: Assigns highest priority tasks to available agent slots
5. **Execution**: Runs `aegis do` subprocess for each task
6. **Monitoring**: Tracks execution via display and web dashboard
7. **Completion**: Updates database, posts results to Asana

**Key Classes**:
```python
class TaskQueue:
    """Priority queue for managing tasks"""
    async def add_tasks(tasks: list[AsanaTask]) -> None
    async def get_next_task() -> tuple[AsanaTask, TaskScore] | None
    async def remove_task(task_gid: str) -> None

class AgentPool:
    """Manages concurrent execution slots"""
    async def can_accept_task() -> bool
    async def add_task(task_gid: str, task_coro: asyncio.Task) -> None
    async def remove_task(task_gid: str) -> None

class Orchestrator:
    """Main orchestration engine"""
    async def run() -> None  # Main entry point
    async def _poll_loop() -> None  # Fetch tasks
    async def _dispatch_loop() -> None  # Assign tasks
    async def _execute_task(task, score) -> None  # Run task
```

**Configuration** (from `config.py`):
- `poll_interval_seconds`: Polling frequency (default: 30)
- `max_concurrent_tasks`: Max parallel executions (default: 5)
- `execution_mode`: "simple_executor" or "claude_cli" (default: "simple_executor")
- `shutdown_timeout`: Shutdown grace period in seconds (default: 300)

**Tests**: Integration tests in `tests/integration/test_e2e.py`

### 8. Web Dashboard (`src/aegis/orchestrator/web.py`) - 590 lines

**Purpose**: Real-time web interface for monitoring orchestrator

**Features**:
- **Live Status**: Orchestrator state, project info, PID
- **Statistics**: Total dispatched, completed, failed, launched
- **Active Agents**: List of currently executing tasks with:
  - Task name and GID
  - Execution status (dispatched, in_progress, running)
  - Duration counter
  - Log file path
  - Real-time log preview (last 20 lines)
- **WebSocket Updates**: Real-time data streaming every second
- **Auto-refresh**: Polls agents endpoint every 2 seconds
- **Dark Theme**: GitHub-inspired dark UI

**API Endpoints**:
```python
GET  /              # Dashboard HTML page
GET  /api/status    # Orchestrator status JSON
GET  /api/agents    # Active agents JSON
GET  /api/logs/{task_gid}  # Task log content
WS   /ws            # WebSocket for real-time updates
```

**Access**:
```bash
# Start orchestrator (web server starts automatically)
aegis start Aegis

# Dashboard URL shown in output:
# 🌐 Web Dashboard: http://127.0.0.1:8000
```

**Dashboard Sections**:
1. **Header**: Project name, status badge (running/stopped), PID
2. **Stats Grid**: Dispatched, Completed, Failed, Poll Interval cards
3. **Active Agents**: Real-time list of executing tasks with logs

**Technology**:
- **Framework**: FastAPI with Uvicorn
- **WebSockets**: For real-time updates
- **Frontend**: Vanilla JavaScript, no dependencies
- **Styling**: Embedded CSS (GitHub dark theme)

### 9. Database Sync (`src/aegis/sync/asana_sync.py`) - 294 lines

**Purpose**: Synchronize Asana data into local PostgreSQL database

**Features**:
- **Portfolio Sync**: Syncs all projects from configured portfolio
- **Task Sync**: Syncs all tasks for each project
- **Incremental Updates**: Uses `last_synced_at` timestamps
- **Idempotent**: Re-running updates existing records
- **System State Tracking**: Records last sync times

**Usage**:
```bash
# Sync all projects and tasks
aegis sync

# Sync only projects (skip tasks)
aegis sync --projects-only
```

**Functions**:
```python
async def sync_portfolio_projects(
    client: AsanaClient,
    portfolio_gid: str,
    workspace_gid: str,
    session: Session | None = None,
) -> list[Project]

async def sync_project_tasks(
    client: AsanaClient,
    project: Project,
    session: Session | None = None,
) -> list[Task]

async def sync_all(
    portfolio_gid: str | None = None,
    workspace_gid: str | None = None,
) -> tuple[list[Project], list[Task]]
```

**What Gets Synced**:
- **Projects**: name, notes, archived status, portfolio/workspace GIDs
- **Tasks**: name, description, HTML notes, completion status, due dates, assignee, parent task, subtasks, tags, custom fields

**Database Tables Updated**:
- `projects` - Asana projects
- `tasks` - Asana tasks
- `system_state` - Last sync timestamps

### 10. SimpleExecutor Agent (`src/aegis/agents/simple_executor.py`) - 398 lines

**Purpose**: Claude API-based agent for task execution

**Features**:
- **Direct Claude API**: Uses Anthropic Python SDK (Messages API)
- **Prompt Generation**: Converts Asana tasks to Claude prompts
- **Response Formatting**: Posts formatted results to Asana
- **Database Logging**: Records all executions with token usage
- **Error Handling**: Retry logic with exponential backoff
- **Long Response Splitting**: Handles Asana's 65K character limit

**Usage**:
```python
from aegis.agents.simple_executor import SimpleExecutor
from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaTask

# Initialize
executor = SimpleExecutor()

# Execute task
result = await executor.execute_task(
    task=task,
    project_name="Aegis",
    code_path="/Users/daveey/code/aegis"
)

# Result contains:
# - success: bool
# - output: str (response text)
# - error: str | None
# - execution_id: int
# - metadata: dict (token usage, etc.)
```

**Key Methods**:
```python
def _generate_prompt(task, project_name, code_path) -> str
    """Generate Claude prompt from Asana task"""

async def _call_claude_api(prompt: str) -> tuple[str, dict]
    """Call Claude API and return response + metadata"""

async def _post_response_to_asana(task_gid, response_text, status) -> None
    """Post response to Asana with retry logic"""

def _log_execution(task_gid, status, started_at, ...) -> TaskExecution
    """Log execution to database"""

async def execute_task(task, project_name, code_path) -> dict
    """Main entry point - orchestrates full execution"""
```

**Configuration**:
- `anthropic_api_key`: Claude API key
- `anthropic_model`: Model to use (default: claude-sonnet-4-5-20250929)
- `DEFAULT_MAX_TOKENS`: 4096
- `DEFAULT_TEMPERATURE`: 1.0

**Database Tracking**: Creates `TaskExecution` records with:
- Status, agent_type, timing info
- Input/output token counts
- Cost estimation
- Success/failure status
- Error messages if failed

### 11. Database CRUD (`src/aegis/database/crud.py`) - 989 lines

**Purpose**: Complete CRUD operations for all database models

**Operations Available**:

**Projects**:
- `create_project()` - Create new project
- `get_project_by_gid()` - Find by Asana GID
- `get_all_projects()` - List all projects (with filters)
- `update_project()` - Update fields
- `get_or_create_project()` - Idempotent create

**Tasks**:
- `create_task()` - Create new task
- `get_task_by_gid()` - Find by Asana GID
- `get_tasks_by_project()` - List tasks for project
- `update_task()` - Update fields
- `mark_task_complete()` - Mark as completed
- `get_or_create_task()` - Idempotent create

**Task Executions**:
- `create_task_execution()` - Create execution record
- `get_task_executions_by_task()` - List executions
- `update_task_execution_status()` - Update status/results

**Features**:
- Session management (optional session parameter)
- Proper error handling with custom exceptions
- Structured logging
- Transaction rollback on errors
- Context manager support

**Custom Exceptions**:
```python
class NotFoundError(Exception): pass
class DuplicateError(Exception): pass
```

---

## Development Workflow

### 1. Setting Up Development Environment

```bash
# Clone and setup
git clone <repo>
cd aegis

# Create virtual environment with uv
uv venv
source .venv/bin/activate

# Install dependencies
uv pip install -e .

# Setup environment
cp .env.example .env
# Edit .env with your credentials

# Setup database
docker compose up -d postgres
# Or use local PostgreSQL: brew install postgresql@16

# Create database
createdb aegis

# Run migrations (if any)
alembic upgrade head

# Test the setup
aegis config
aegis test-asana
```

### 2. Making Changes

**Before You Start**:
1. Check if there's already a related Asana task
2. Review relevant documentation in `docs/` or `design/`
3. Check existing tests in `tests/`

**Development Cycle**:
```bash
# 1. Make your changes
vim src/aegis/cli.py

# 2. Run relevant tests
pytest tests/unit/test_cli.py -v

# 3. Check syntax
uv run python -c "import ast; ast.parse(open('src/aegis/cli.py').read())"

# 4. Verify CLI works
aegis --help
aegis config

# 5. Test integration (if needed)
pytest tests/integration/test_e2e.py::TestCLIIntegration -v

# 6. Check coverage
pytest tests/unit/ --cov=src/aegis --cov-report=term-missing
```

### 3. Common Development Tasks

**Adding a New CLI Command**:
```python
# In src/aegis/cli.py

@main.command()
@click.argument("project_name")
@click.option("--flag", is_flag=True, help="Description")
def my_command(project_name: str, flag: bool) -> None:
    """Command description."""
    config = Settings()
    # Implementation
```

**Adding a New Asana API Method**:
```python
# In src/aegis/asana/client.py

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
async def my_method(self, arg: str) -> ReturnType:
    """Method description."""
    try:
        response = await asyncio.to_thread(
            self.api.method,
            arg,
            {"opt_fields": "field1,field2"}
        )
        # Process response
        logger.info("method_success", arg=arg)
        return result
    except ApiException as e:
        logger.error("method_error", error=str(e), arg=arg)
        raise
```

**Adding a Database Model**:
```python
# In src/aegis/database/models.py

class MyModel(Base):
    """Model description."""
    __tablename__ = "my_table"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    data: Mapped[str]
```

Then create migration:
```bash
alembic revision --autogenerate -m "Add my_table"
alembic upgrade head
```

---

## Testing Guidelines

### Test Organization

```
tests/
├── unit/                       # Fast, isolated tests
│   ├── test_prioritizer.py    # 36 tests
│   ├── test_shutdown.py        # 29 tests
│   └── test_config.py          # 15 tests
│
└── integration/                # Slower, integration tests
    ├── test_e2e.py             # 14 E2E tests
    ├── E2E_TEST_GUIDE.md       # Complete guide
    └── TEST_SUMMARY.md         # Overview
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/unit/test_prioritizer.py -v

# Run specific test
pytest tests/unit/test_prioritizer.py::test_overdue_task_priority -v

# Run with coverage
pytest tests/unit/ --cov=src/aegis --cov-report=html

# Run integration tests
pytest tests/integration/ -v

# Run CLI integration tests (no setup needed)
pytest tests/integration/test_e2e.py::TestCLIIntegration -v
```

### Test Markers

```python
@pytest.mark.unit          # Fast, isolated tests
@pytest.mark.integration   # Integration tests
@pytest.mark.live          # Tests that call live APIs (cost money)
@pytest.mark.slow          # Tests that take >1 second
```

### Writing Tests

**Unit Test Example**:
```python
import pytest
from aegis.asana.client import AsanaClient

@pytest.mark.unit
def test_parse_task():
    """Test task parsing."""
    client = AsanaClient("fake_token")
    task_data = {
        "gid": "123",
        "name": "Test Task",
        "completed": False
    }
    task = client._parse_task(task_data)
    assert task.gid == "123"
    assert task.name == "Test Task"
```

**Integration Test Example**:
```python
import pytest
from aegis.asana.client import AsanaClient
from aegis.config import Settings

@pytest.mark.integration
@pytest.mark.asyncio
async def test_fetch_tasks():
    """Test fetching tasks from Asana."""
    config = Settings()
    client = AsanaClient(config.asana_access_token)

    tasks = await client.get_tasks_from_project(
        config.asana_test_project_gid
    )

    assert len(tasks) > 0
    assert all(hasattr(t, 'gid') for t in tasks)
```

### Test Coverage Goals

- **Unit tests**: Aim for 90%+ coverage
- **Integration tests**: Cover critical user workflows
- **Current status**:
  - prioritizer.py: 92% coverage ✅
  - shutdown.py: 91% coverage ✅
  - asana/client.py: ~70% coverage (needs improvement)

---

## Common Patterns

### 1. Async/Await Pattern

All I/O operations use async/await:
```python
# Async function
async def fetch_data():
    result = await async_operation()
    return result

# Running async code
import asyncio
asyncio.run(fetch_data())

# Or in Click commands
def my_command():
    result = asyncio.run(_my_command_async())

async def _my_command_async():
    # Async implementation
    pass
```

### 2. Structured Logging

Use structlog throughout:
```python
import structlog
logger = structlog.get_logger()

# Info logging
logger.info("operation_success", task_id=task_id, count=5)

# Warning logging
logger.warning("operation_warning", task_id=task_id, reason="timeout")

# Error logging
logger.error("operation_failed", task_id=task_id, error=str(e))

# Debug logging
logger.debug("operation_detail", task_id=task_id, details=data)
```

### 3. Configuration Access

Always use Settings:
```python
from aegis.config import Settings

config = Settings()  # Loads from .env
client = AsanaClient(config.asana_access_token)
```

### 4. Database Session Management

Use async context manager:
```python
from aegis.database.session import get_async_session
from aegis.database.models import TaskExecution

async with get_async_session() as session:
    execution = TaskExecution(
        task_id=task_gid,
        status="in_progress"
    )
    session.add(execution)
    await session.commit()
```

### 5. Error Handling

Use try/except with structured logging:
```python
try:
    result = await operation()
    logger.info("operation_success", result=result)
    return result
except SpecificException as e:
    logger.error("operation_failed", error=str(e), context=ctx)
    # Handle or re-raise
    raise
```

### 6. Subprocess Management

Use ShutdownHandler for tracking:
```python
from aegis.utils.shutdown import get_shutdown_handler

shutdown_handler = get_shutdown_handler()
process = subprocess.Popen(["command"])
shutdown_handler.track_subprocess(process)

try:
    stdout, stderr = process.communicate(timeout=300)
finally:
    shutdown_handler.untrack_subprocess(process)
```

---

## Important Conventions

### 1. Code Style

- **Formatting**: Follow PEP 8 (Black formatter compatible)
- **Type hints**: Use type hints for all function signatures
- **Docstrings**: Google style docstrings for public methods
- **Line length**: 100 characters max (not strict)

### 2. Naming Conventions

- **Functions**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private methods**: `_leading_underscore`
- **Async functions**: No special prefix (rely on `async def`)

### 3. Import Organization

```python
# Standard library
import asyncio
from datetime import datetime

# Third-party packages
import asana
import structlog
from pydantic import Field

# Local imports
from aegis.asana.client import AsanaClient
from aegis.config import Settings
```

### 4. CLI Command Structure

```python
@main.command()
@click.argument("required_arg")
@click.option("--flag", is_flag=True, help="Description")
@click.option("--value", default="default", help="Description")
def command_name(required_arg: str, flag: bool, value: str) -> None:
    """Command description.

    Longer description if needed.
    """
    # Implementation using asyncio.run for async code
    asyncio.run(_command_name_async(required_arg, flag, value))

async def _command_name_async(required_arg: str, flag: bool, value: str) -> None:
    """Async implementation."""
    # Async code here
```

### 5. Database Operations

- Use async sessions
- Commit explicitly
- Handle connection cleanup in shutdown
- Use SQLAlchemy 2.0 style (Mapped types)

### 6. Asana API Calls

- All calls use `asyncio.to_thread` wrapper
- Retry logic with exponential backoff
- Structured logging for all operations
- `opts` dict for parameters (not kwargs)

---

## Troubleshooting

### Common Issues

#### 1. Import Errors

**Problem**: `ImportError: cannot import name 'Settings'`

**Solution**: Make sure you're using the correct import:
```python
from aegis.config import Settings  # Correct
# NOT: from aegis.config import get_config
```

#### 2. Asana API Errors

**Problem**: `TasksApi.method() takes 3 positional arguments but 4 were given`

**Solution**: Use `opts` dict format:
```python
# Correct:
await asyncio.to_thread(
    api.method,
    required_arg,
    {"opt_fields": "field1,field2"}
)

# Incorrect:
await asyncio.to_thread(
    api.method,
    {"data": {...}},
    required_arg,
    {}
)
```

#### 3. Database Connection Issues

**Problem**: `could not connect to server: Connection refused`

**Solution**:
```bash
# Start PostgreSQL
docker compose up -d postgres

# Or if using local PostgreSQL
brew services start postgresql@16

# Verify it's running
psql -h localhost -U postgres -l
```

#### 4. Missing Environment Variables

**Problem**: `ValidationError: field required`

**Solution**: Check your `.env` file has all required variables:
```bash
# Copy from example
cp .env.example .env

# Edit with your credentials
vim .env

# Verify configuration
aegis config
```

#### 5. Terminal Mode Permission Errors

**Problem**: `osascript is not allowed to send keystrokes`

**Solution**: Grant accessibility permissions in System Settings → Privacy & Security → Accessibility

#### 6. Task Not Marked Complete in Asana

**Problem**: Task executed successfully but not marked complete

**Solution**: This was fixed in commit `16:37`. The `aegis work-on` command now automatically calls `complete_task_and_move_to_implemented()` after successful execution (see cli.py:908-921).

---

## Useful Commands

### Development
```bash
# Install in development mode
uv pip install -e .

# Run CLI
aegis --help
aegis config

# Check syntax
uv run python -c "import ast; ast.parse(open('src/aegis/cli.py').read())"

# Format code (if Black is installed)
black src/aegis/

# Type checking (if mypy is installed)
mypy src/aegis/
```

### Testing
```bash
# All tests
pytest

# With coverage
pytest --cov=src/aegis --cov-report=html

# Specific test file
pytest tests/unit/test_prioritizer.py -v

# Watch mode (if pytest-watch is installed)
ptw tests/unit/
```

### Database
```bash
# Create database
createdb aegis

# Create test database
createdb aegis_test

# Run migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "Description"

# Rollback
alembic downgrade -1
```

### Docker Services
```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f postgres

# Restart service
docker compose restart postgres
```

---

## Quick Reference

### File Locations

| What | Where |
|------|-------|
| Main CLI | `src/aegis/cli.py` |
| Asana Client | `src/aegis/asana/client.py` |
| Configuration | `src/aegis/config.py` |
| Database Models | `src/aegis/database/models.py` |
| Shutdown Handler | `src/aegis/utils/shutdown.py` |
| Prioritizer | `src/aegis/orchestrator/prioritizer.py` |
| Unit Tests | `tests/unit/` |
| Integration Tests | `tests/integration/` |
| Documentation | `docs/` |
| Design Docs | `design/` |
| Logs | `logs/aegis.log` |

### Important GIDs

| Entity | GID (from config) |
|--------|-------------------|
| Aegis Project | 1212085431574340 |
| Workspace | From ASANA_WORKSPACE_GID |
| Portfolio | From ASANA_PORTFOLIO_GID |

### Standard Sections

Projects should have these sections (created by `aegis organize`):
1. Waiting for Response
2. Ready to Implement
3. In Progress
4. Implemented
5. Answered
6. Ideas

---

## Additional Resources

### Documentation Files

- `README.md` - Project overview
- `CLAUDE.md` - This file - AI assistant guide
- `PROJECT_STRUCTURE.md` - **Complete codebase map (file-by-file documentation)**
- `TOOLS.md` - CLI reference
- `docs/OPERATOR_GUIDE.md` - Complete operator guide
- `docs/SHUTDOWN_HANDLING.md` - Shutdown implementation
- `docs/PRIORITIZATION.md` - Task prioritization
- `design/PROJECT_OVERVIEW.md` - Project vision
- `design/TASK_LIST.md` - Detailed roadmap
- `design/ORCHESTRATION.md` - Orchestration architecture
- `tests/integration/E2E_TEST_GUIDE.md` - Testing guide

### Implementation Summaries

- `E2E_IMPLEMENTATION_SUMMARY.md` - E2E testing implementation
- `SHUTDOWN_IMPLEMENTATION_SUMMARY.md` - Shutdown implementation
- `PRIORITIZATION_IMPLEMENTATION_SUMMARY.md` - Prioritization implementation
- `TASK_PRIORITIZATION_COMPLETION_REPORT.md` - Prioritization completion report
- `E2E_INTEGRATION_TEST_COMPLETION_REPORT.md` - E2E test completion report

### Git Workflow

```bash
# Check status
git status

# Stage changes
git add src/aegis/cli.py

# Commit
git commit -m "feat: add new command

- Description of changes
- Why the change was needed"

# Push
git push origin master
```

---

## Questions or Issues?

If you encounter issues or have questions:

1. Check this file first (CLAUDE.md)
2. Review relevant documentation in `docs/`
3. Check design documents in `design/`
4. Look at existing tests for examples
5. Check the logs in `logs/aegis.log`
6. Review recent git commits for similar changes

---

**This document is maintained as the primary reference for AI assistants working on Aegis. Update it when making significant changes to architecture, conventions, or workflows.**
