# Aegis Project Structure

**Last Updated**: 2025-11-28
**Purpose**: Comprehensive file-by-file documentation for LLM/AI assistant use

This document provides a complete map of the Aegis codebase, describing every significant file, its purpose, size, and relationships to other components.

---

## Quick Stats

- **Total Python Files**: 57
- **Total Lines of Code**: ~18,666
- **Source Code**: 38 files (~11,500 LOC)
- **Test Code**: 11 files (~5,300 LOC)
- **Scripts**: 13 utility scripts (~1,900 LOC)

---

## Directory Structure

```
aegis/
├── .env                        # Environment configuration (secrets) - NOT in git
├── .env.example                # Template for environment variables
├── .env.test                   # Test environment configuration
├── .github/                    # GitHub Actions workflows
│   └── workflows/
│       └── integration-tests.yml.example
├── pyproject.toml              # Python project config & dependencies (uv-based)
├── alembic.ini                 # Database migration configuration
├── docker-compose.yml          # Local services (PostgreSQL, Redis)
├── README.md                   # Project overview
├── TOOLS.md                    # CLI command reference
├── CLAUDE.md                   # AI assistant guide (you're using this!)
├── PROJECT_STRUCTURE.md        # This file - complete codebase map
│
├── src/aegis/                  # Main source code
│   ├── __init__.py             # Package init (3 lines)
│   ├── cli.py                  # ⭐ Main CLI entry point (2,575 lines)
│   ├── config.py               # Settings & env management (127 lines)
│   ├── agent_helpers.py        # Agent utility functions (47 lines)
│   │
│   ├── asana/                  # Asana API integration
│   │   ├── __init__.py         # Package exports (21 lines)
│   │   ├── client.py           # ⭐ AsanaClient API wrapper (910 lines)
│   │   └── models.py           # Pydantic models for Asana (117 lines)
│   │
│   ├── database/               # Database layer (PostgreSQL)
│   │   ├── __init__.py         # Package exports (31 lines)
│   │   ├── models.py           # ⭐ SQLAlchemy ORM models (347 lines)
│   │   ├── session.py          # Session management (112 lines)
│   │   ├── state.py            # System state functions (216 lines)
│   │   └── crud.py             # ⭐ Complete CRUD operations (988 lines)
│   │
│   ├── orchestrator/           # Task orchestration engine
│   │   ├── __init__.py         # Package exports (13 lines)
│   │   ├── main.py             # ⭐ Main orchestrator loop (1,153 lines)
│   │   ├── prioritizer.py      # ⭐ Task prioritization (384 lines)
│   │   ├── display.py          # Live console display (246 lines)
│   │   ├── agent_client.py     # Agent execution wrapper (289 lines)
│   │   └── web.py              # ⭐ Web dashboard (988 lines)
│   │
│   ├── agents/                 # AI agents
│   │   ├── __init__.py         # Package exports (1 line)
│   │   ├── simple_executor.py  # ⭐ Claude API agent (397 lines)
│   │   ├── agent_service.py    # Agent service orchestration (316 lines)
│   │   ├── prompts.py          # Prompt templates (331 lines)
│   │   └── formatters.py       # ⭐ Output formatters (406 lines)
│   │
│   ├── sync/                   # Asana sync to local DB
│   │   ├── __init__.py         # Package exports (5 lines)
│   │   └── asana_sync.py       # Sync implementation (293 lines)
│   │
│   └── utils/                  # Utilities
│       ├── __init__.py         # Package exports (1 line)
│       └── shutdown.py         # ⭐ Graceful shutdown handler (385 lines)
│
├── tests/                      # Test suite
│   ├── __init__.py             # Package init (1 line)
│   ├── conftest.py             # Pytest fixtures (63 lines)
│   ├── manual_shutdown_test.py # Manual shutdown testing (277 lines)
│   │
│   ├── unit/                   # Unit tests (fast, isolated)
│   │   ├── __init__.py         # Package init (1 line)
│   │   ├── test_config.py      # Config tests (140 lines)
│   │   ├── test_asana_client.py # Asana client tests (200 lines)
│   │   ├── test_asana_models.py # Asana model tests (160 lines)
│   │   ├── test_crud.py        # ⭐ CRUD tests (1,115 lines)
│   │   ├── test_formatters.py  # Formatter tests (479 lines)
│   │   ├── test_orchestrator.py # Orchestrator tests (492 lines)
│   │   ├── test_prioritizer.py # ⭐ Prioritizer tests (529 lines)
│   │   ├── test_shutdown.py    # ⭐ Shutdown tests (472 lines)
│   │   └── test_simple_executor.py # SimpleExecutor tests (409 lines)
│   │
│   └── integration/            # Integration tests (slower, external deps)
│       ├── __init__.py         # Package init (1 line)
│       ├── test_e2e.py         # ⭐ E2E integration tests (1,123 lines)
│       ├── E2E_TEST_GUIDE.md   # Complete E2E testing guide
│       ├── E2E_STATUS.md       # Current E2E test status
│       ├── TEST_SUMMARY.md     # Test overview
│       └── QUICK_START.md      # Quick start for testing
│
├── scripts/                    # Utility scripts
│   ├── setup_asana.py          # Asana project setup (88 lines)
│   ├── create_project.py       # Create Asana project (131 lines)
│   ├── add_project_to_portfolio.py # Add single project (58 lines)
│   ├── add_projects_to_portfolio.py # Add multiple projects (89 lines)
│   ├── list_workspace_projects.py # List projects (89 lines)
│   ├── populate_tasks.py       # Populate test tasks (595 lines)
│   ├── cleanup_test_tasks.py   # Clean up test data (186 lines)
│   ├── complete_task.py        # Complete a task (151 lines)
│   ├── populate_prompt_templates.py # Populate prompts (416 lines)
│   ├── test_prompts.py         # Test prompt generation (244 lines)
│   └── uncomplete_failed_tasks.py # Uncomplete failed tasks (129 lines)
│
├── alembic/                    # Database migrations
│   ├── env.py                  # Alembic environment (84 lines)
│   └── versions/               # Migration scripts
│       └── 22bba2d16585_initial_schema_system_state_task_.py (242 lines)
│
├── docs/                       # Documentation
│   ├── OPERATOR_GUIDE.md       # Complete operator guide
│   ├── SHUTDOWN_HANDLING.md    # Shutdown implementation docs
│   ├── PRIORITIZATION.md       # Task prioritization docs
│   ├── QUESTION_AUTO_COMPLETE.md # Question auto-completion
│   └── AGENT_COMMAND.md        # Agent command documentation
│
├── design/                     # Design documents
│   ├── PROJECT_OVERVIEW.md     # Project vision and architecture
│   ├── TASK_LIST.md            # Detailed implementation roadmap
│   ├── DATABASE_SCHEMA.md      # Database design
│   ├── ORCHESTRATION.md        # Orchestration architecture
│   └── AUTONOMOUS_WORK_PATTERN.md # Autonomous execution pattern
│
├── examples/                   # Example configurations
│   └── README.md               # Examples overview
│
└── logs/                       # Execution logs
    └── aegis.log               # Main log file (appended by each run)
```

---

## Core Source Files (src/aegis/)

### 1. cli.py (2,575 lines) ⭐ MAIN ENTRY POINT

**Purpose**: Main CLI interface - all commands start here

**Key Commands**:
- `aegis config` - Display configuration
- `aegis test-asana` - Test Asana connection
- `aegis test-claude` - Test Claude API
- `aegis do <task_or_project>` - Execute single task
- `aegis work-on <project>` - Autonomous multi-task execution
- `aegis start <project>` - Start orchestrator daemon
- `aegis organize <task_or_project>` - Apply section structure
- `aegis plan <task_or_project>` - Review and plan tasks
- `aegis sync` - Sync Asana to local DB
- `aegis create-agents-project` - Create Agents project
- `aegis process-agent-mentions <project>` - Monitor @-mentions

**Important Functions**:
```python
# Lines vary, but key functions:
def do(project_name, terminal) -> None               # Single task execution
def work_on(project_name, max_tasks, dry_run) -> None # Autonomous execution
def start(project_name) -> None                       # Start orchestrator
def organize(project_name) -> None                    # Apply sections
def plan(project_name, target_ready) -> None          # Task planning
def sync() -> None                                    # Sync Asana data
def launch_in_hyper_terminal(command, cwd) -> int     # Terminal mode
```

**Dependencies**: All other modules (orchestrator, asana, agents, database, etc.)

**When to modify**: Adding new CLI commands, changing user-facing behavior

---

### 2. asana/client.py (910 lines) ⭐ ASANA API WRAPPER

**Purpose**: Complete wrapper around Asana Python SDK with async support

**Key Classes**:
```python
class AsanaClient:
    # Task operations
    async def get_tasks_from_project(project_gid, assigned_only=False)
    async def get_task(task_gid)
    async def update_task(task_gid, updates: AsanaTaskUpdate)
    async def complete_task_and_move_to_implemented(task_gid, project_gid)

    # Comment operations
    async def add_comment(task_gid, text)
    async def get_comments(task_gid)

    # Project operations
    async def get_project(project_gid)
    async def get_sections(project_gid)
    async def create_section(project_gid, section_name)
    async def move_task_to_section(task_gid, project_gid, section_gid)

    # Dependency operations
    async def add_dependency(task_gid, depends_on_gid)
    async def remove_dependency(dependency_gid)

    # Utility operations
    async def ensure_project_sections(project_gid, section_names)
    async def get_projects_in_portfolio(portfolio_gid)
```

**Features**:
- Automatic retry with exponential backoff (3 attempts)
- Async wrapper around synchronous Asana SDK
- Structured logging for all operations
- Consistent error handling

**Dependencies**: asana SDK, asyncio, tenacity, structlog

**When to modify**: Adding new Asana API endpoints, changing retry logic

---

### 3. asana/models.py (117 lines)

**Purpose**: Pydantic models for Asana entities

**Models**:
```python
class AsanaTask(BaseModel):
    gid: str
    name: str
    notes: str | None
    html_notes: str | None
    completed: bool
    due_on: str | None
    due_at: str | None
    assignee: dict | None
    parent: dict | None
    dependencies: list[dict]
    dependents: list[dict]
    tags: list[dict]
    custom_fields: list[dict]
    memberships: list[dict]
    created_at: str
    modified_at: str

class AsanaProject(BaseModel):
    gid: str
    name: str
    notes: str | None
    archived: bool
    # ... other fields

class AsanaSection(BaseModel):
    gid: str
    name: str
    # ... other fields

class AsanaComment(BaseModel):
    gid: str
    text: str
    created_at: str
    # ... other fields

class AsanaTaskUpdate(BaseModel):
    # Used for partial updates
    completed: bool | None
    name: str | None
    notes: str | None
    # ... other optional fields
```

**Dependencies**: pydantic

**When to modify**: Adding new Asana fields, changing data validation

---

### 4. config.py (127 lines)

**Purpose**: Environment configuration using Pydantic Settings

**Key Class**:
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
    shutdown_timeout: int = 300

    # Task Prioritization (weighted factors)
    priority_weight_due_date: float = 10.0
    priority_weight_dependencies: float = 8.0
    priority_weight_user_priority: float = 7.0
    priority_weight_project: float = 5.0
    priority_weight_age: float = 3.0

    class Config:
        env_file = ".env"
```

**Usage**: `config = Settings()` - loads from .env file

**Dependencies**: pydantic-settings

**When to modify**: Adding new configuration parameters

---

### 5. database/models.py (347 lines) ⭐ DATABASE SCHEMA

**Purpose**: SQLAlchemy ORM models for all database tables

**Models**:

```python
class SystemState(Base):
    """Global system state tracking"""
    __tablename__ = "system_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    orchestrator_pid: Mapped[int | None]
    orchestrator_status: Mapped[str]  # "running" | "stopped"
    last_poll_time: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

class Project(Base):
    """Asana projects synced to local DB"""
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    gid: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    notes: Mapped[str | None]
    archived: Mapped[bool]
    portfolio_gid: Mapped[str | None]
    workspace_gid: Mapped[str | None]
    last_synced_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Relationships
    tasks: Mapped[list["Task"]] = relationship(back_populates="project")

class Task(Base):
    """Asana tasks synced to local DB"""
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    gid: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    notes: Mapped[str | None]
    html_notes: Mapped[str | None]
    completed: Mapped[bool]
    due_on: Mapped[str | None]
    due_at: Mapped[datetime | None]
    assignee_gid: Mapped[str | None]
    parent_gid: Mapped[str | None]
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    last_synced_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="tasks")
    executions: Mapped[list["TaskExecution"]] = relationship(back_populates="task")

class TaskExecution(Base):
    """Task execution history"""
    __tablename__ = "task_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str]  # Asana GID (not FK - allows external tasks)
    status: Mapped[str]  # "pending" | "in_progress" | "completed" | "failed"
    agent_type: Mapped[str | None]  # "simple_executor" | "claude_cli"
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    duration_seconds: Mapped[float | None]
    success: Mapped[bool | None]
    error_message: Mapped[str | None]
    output: Mapped[str | None]
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cost_usd: Mapped[float | None]
    context: Mapped[dict | None]  # JSON field
    execution_metadata: Mapped[dict | None]  # JSON field
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]

class CommentLog(Base):
    """Comments posted to Asana"""
    __tablename__ = "comment_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[str]
    comment_id: Mapped[str]
    comment_text: Mapped[str]
    posted_at: Mapped[datetime]
    created_at: Mapped[datetime]
```

**Dependencies**: SQLAlchemy 2.0, PostgreSQL

**When to modify**: Adding new database tables, changing schema

---

### 6. database/crud.py (988 lines) ⭐ COMPLETE CRUD OPERATIONS

**Purpose**: All database CRUD operations with error handling

**Key Functions**:

```python
# Projects
def create_project(session, **kwargs) -> Project
def get_project_by_gid(session, gid: str) -> Project | None
def get_all_projects(session, ...) -> list[Project]
def update_project(session, gid: str, **kwargs) -> Project
def get_or_create_project(session, gid: str, ...) -> tuple[Project, bool]

# Tasks
def create_task(session, **kwargs) -> Task
def get_task_by_gid(session, gid: str) -> Task | None
def get_tasks_by_project(session, project_gid: str) -> list[Task]
def update_task(session, gid: str, **kwargs) -> Task
def mark_task_complete(session, gid: str) -> Task
def get_or_create_task(session, gid: str, ...) -> tuple[Task, bool]

# Task Executions
def create_task_execution(session, **kwargs) -> TaskExecution
def get_task_executions_by_task(session, task_gid: str) -> list[TaskExecution]
def update_task_execution_status(session, execution_id: int, ...) -> TaskExecution

# System State
def get_system_state(session) -> SystemState
def update_system_state(session, **kwargs) -> SystemState
```

**Features**:
- Optional session parameter (creates new if not provided)
- Custom exceptions (NotFoundError, DuplicateError)
- Structured logging
- Transaction rollback on errors

**Dependencies**: SQLAlchemy, database.models, structlog

**When to modify**: Adding new CRUD operations, changing query patterns

---

### 7. database/session.py (112 lines)

**Purpose**: Database session management

**Key Functions**:
```python
def get_engine() -> Engine
    """Get or create database engine"""

def init_db() -> None
    """Initialize database and create tables"""

def get_session_factory() -> sessionmaker
    """Get or create session factory"""

@contextmanager
def get_db_session() -> Generator[Session, None, None]
    """Context manager for database sessions"""

def get_db() -> Session
    """Get a database session (caller must close)"""

def cleanup_db_connections() -> None
    """Clean up database connections during shutdown"""
```

**Features**:
- Connection pooling (size=5, max_overflow=10)
- Pre-ping connections for health checks
- Automatic commit/rollback in context manager
- Shutdown cleanup support

**Dependencies**: SQLAlchemy

**When to modify**: Changing connection pool settings, session lifecycle

---

### 8. database/state.py (216 lines)

**Purpose**: System state tracking functions

**Key Functions**:
```python
def get_orchestrator_status() -> dict
    """Get current orchestrator status from DB"""

def set_orchestrator_status(status: str, pid: int | None) -> None
    """Update orchestrator status in DB"""

def is_orchestrator_running() -> bool
    """Check if orchestrator is currently running"""

def record_poll_time() -> None
    """Record last poll time"""

def get_last_poll_time() -> datetime | None
    """Get last poll time"""
```

**Dependencies**: database.models, database.session

**When to modify**: Adding new state tracking features

---

### 9. orchestrator/main.py (1,153 lines) ⭐ ORCHESTRATION ENGINE

**Purpose**: Continuous task monitoring and execution engine

**Key Classes**:

```python
class TaskQueue:
    """Priority queue for managing tasks"""
    async def add_tasks(tasks: list[AsanaTask]) -> None
    async def get_next_task() -> tuple[AsanaTask, TaskScore] | None
    async def remove_task(task_gid: str) -> None
    async def get_all_tasks() -> list[tuple[AsanaTask, TaskScore]]

class AgentPool:
    """Manages concurrent execution slots"""
    async def can_accept_task() -> bool
    async def add_task(task_gid: str, task_coro: asyncio.Task) -> None
    async def remove_task(task_gid: str) -> None
    async def get_active_tasks() -> dict[str, dict]

class Orchestrator:
    """Main orchestration engine"""
    async def run() -> None
        """Main entry point - runs until shutdown"""

    async def _poll_loop() -> None
        """Fetch new tasks from Asana"""

    async def _dispatch_loop() -> None
        """Assign tasks to available agents"""

    async def _execute_task(task, score) -> None
        """Execute a single task"""
```

**Features**:
- Priority-based task queue
- Concurrent execution management
- Live console display (rich)
- Web dashboard integration
- Graceful shutdown support
- Multiple execution modes (simple_executor, claude_cli)

**Configuration**:
- `poll_interval_seconds`: Polling frequency (default: 30)
- `max_concurrent_tasks`: Max parallel executions (default: 5)
- `execution_mode`: Agent type (default: "simple_executor")

**Dependencies**: orchestrator.prioritizer, orchestrator.display, orchestrator.web, asana.client, utils.shutdown

**When to modify**: Changing orchestration logic, adding new execution modes

---

### 10. orchestrator/prioritizer.py (384 lines) ⭐ TASK PRIORITIZATION

**Purpose**: Multi-factor task prioritization algorithm

**Key Classes**:

```python
class PriorityConfig:
    """Configuration for priority weights"""
    weight_due_date: float = 10.0
    weight_dependencies: float = 8.0
    weight_user_priority: float = 7.0
    weight_project: float = 5.0
    weight_age: float = 3.0

class TaskScore:
    """Task with priority score"""
    task: AsanaTask
    total_score: float
    component_scores: dict[str, float]
    explanation: str

class TaskPrioritizer:
    """Multi-factor task prioritization"""
    async def prioritize_tasks(
        tasks: list[AsanaTask],
        projects_by_gid: dict[str, AsanaProject]
    ) -> list[tuple[AsanaTask, TaskScore]]
```

**Scoring Factors**:
1. **Due Date Urgency** (weight 10.0) - Overdue tasks get highest priority
2. **Dependencies** (weight 8.0) - Parent tasks prioritized over children
3. **User Priority** (weight 7.0) - Custom field from Asana
4. **Project Importance** (weight 5.0) - Critical projects boosted
5. **Age** (weight 3.0) - Older tasks gradually increase priority

**Test Coverage**: 36 unit tests, 92% coverage

**Dependencies**: asana.models, config

**When to modify**: Changing prioritization algorithm, adding new factors

---

### 11. orchestrator/web.py (988 lines) ⭐ WEB DASHBOARD

**Purpose**: Real-time web interface for monitoring orchestrator

**Key Features**:
- Live status display (orchestrator state, project info, PID)
- Statistics (dispatched, completed, failed, poll interval)
- Active agents list with real-time updates
- Task log preview (last 20 lines per task)
- WebSocket updates every second
- Dark theme (GitHub-inspired)

**API Endpoints**:
```python
GET  /                      # Dashboard HTML page
GET  /api/status            # Orchestrator status JSON
GET  /api/agents            # Active agents JSON
GET  /api/logs/{task_gid}   # Task log content
WS   /ws                    # WebSocket for real-time updates
```

**Technology**: FastAPI, Uvicorn, WebSockets, vanilla JavaScript

**Default Port**: 8000

**Dependencies**: FastAPI, uvicorn, websockets

**When to modify**: Adding new dashboard features, changing UI

---

### 12. orchestrator/display.py (246 lines)

**Purpose**: Live console display using Rich library

**Key Classes**:
```python
class OrchestratorDisplay:
    """Full-screen rich console display"""
    def start() -> None
    def stop() -> None
    def update() -> None
    def _generate_layout() -> Layout
```

**Features**:
- Full-screen terminal UI
- Real-time updates
- Statistics panel
- Active tasks panel
- Auto-refresh every 0.5 seconds

**Dependencies**: rich

**When to modify**: Changing console display layout

---

### 13. orchestrator/agent_client.py (289 lines)

**Purpose**: Wrapper for executing agents as subprocesses

**Key Functions**:
```python
async def execute_task_with_agent(
    task: AsanaTask,
    project_name: str,
    agent_type: str = "simple_executor",
    log_to_file: bool = True
) -> dict
    """Execute task using specified agent"""
```

**Features**:
- Subprocess management
- Log file capture
- Timeout handling
- Graceful shutdown integration

**Dependencies**: utils.shutdown, asyncio

**When to modify**: Changing agent execution behavior

---

### 14. agents/simple_executor.py (397 lines) ⭐ CLAUDE API AGENT

**Purpose**: Direct Claude API-based task execution

**Key Class**:
```python
class SimpleExecutor:
    """Claude API agent for task execution"""

    async def execute_task(
        task: AsanaTask,
        project_name: str,
        code_path: str
    ) -> dict:
        """Main entry point - orchestrates full execution"""
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
```

**Features**:
- Direct Anthropic Python SDK (Messages API)
- Automatic response formatting
- Database logging with token usage
- Retry logic with exponential backoff
- Handles 65K Asana comment limit

**Configuration**:
- `anthropic_api_key`: Claude API key
- `anthropic_model`: Model (default: claude-sonnet-4-5-20250929)
- `DEFAULT_MAX_TOKENS`: 4096
- `DEFAULT_TEMPERATURE`: 1.0

**Dependencies**: anthropic, asana.client, database.crud, agents.formatters

**When to modify**: Changing prompt generation, API call behavior

---

### 15. agents/formatters.py (406 lines)

**Purpose**: Format agent responses for Asana comments

**Key Functions**:
```python
def format_success_response(
    output: str,
    agent_type: str,
    duration_seconds: float,
    execution_id: int,
    metadata: dict | None = None
) -> str
    """Format successful execution response"""

def format_error_response(
    error: Exception | str,
    agent_type: str,
    duration_seconds: float,
    context: dict | None = None
) -> str
    """Format error response"""

def split_long_response(text: str, max_length: int = 60000) -> list[str]
    """Split long responses into multiple comments"""
```

**Features**:
- Markdown formatting
- Token usage display
- Cost estimation
- Error context formatting
- Long response splitting

**Test Coverage**: 479 lines of tests

**Dependencies**: None (pure Python)

**When to modify**: Changing response formatting, adding new templates

---

### 16. agents/prompts.py (331 lines)

**Purpose**: Prompt templates for agents

**Key Functions**:
```python
def get_task_execution_prompt(
    task: AsanaTask,
    project_name: str,
    code_path: str,
    dependencies: list[AsanaTask] | None = None
) -> str
    """Generate execution prompt from task"""

def get_question_prompt(
    question: str,
    context: dict | None = None
) -> str
    """Generate question-answering prompt"""
```

**Features**:
- Template-based prompts
- Context injection
- Dependency information
- Project-specific instructions

**Dependencies**: asana.models

**When to modify**: Changing prompt templates, adding new prompt types

---

### 17. agents/agent_service.py (316 lines)

**Purpose**: Agent service orchestration (future expansion)

**Status**: Partially implemented - designed for multi-agent orchestration

**Dependencies**: agents.simple_executor

**When to modify**: Adding new agent types, multi-agent coordination

---

### 18. sync/asana_sync.py (293 lines)

**Purpose**: Sync Asana data to local PostgreSQL database

**Key Functions**:
```python
async def sync_portfolio_projects(
    client: AsanaClient,
    portfolio_gid: str,
    workspace_gid: str,
    session: Session | None = None
) -> list[Project]
    """Sync all projects from portfolio"""

async def sync_project_tasks(
    client: AsanaClient,
    project: Project,
    session: Session | None = None
) -> list[Task]
    """Sync all tasks for a project"""

async def sync_all(
    portfolio_gid: str | None = None,
    workspace_gid: str | None = None
) -> tuple[list[Project], list[Task]]
    """Sync everything"""
```

**Features**:
- Incremental updates using `last_synced_at`
- Idempotent operations (safe to re-run)
- Batch processing
- System state tracking

**What Gets Synced**:
- Projects: name, notes, archived status, GIDs
- Tasks: name, notes, completion, due dates, assignee, parent, tags, custom fields

**Dependencies**: asana.client, database.crud, database.models

**When to modify**: Adding new fields to sync, changing sync logic

---

### 19. utils/shutdown.py (385 lines) ⭐ GRACEFUL SHUTDOWN

**Purpose**: Handles SIGTERM/SIGINT and coordinates graceful shutdown

**Key Class**:
```python
class ShutdownHandler:
    """Graceful shutdown coordinator"""

    def install_signal_handlers() -> None
    def register_cleanup_callback(callback) -> None
    def track_subprocess(process: subprocess.Popen) -> None
    def untrack_subprocess(process: subprocess.Popen) -> None
    async def shutdown() -> None
```

**Features**:
- Signal handler installation (SIGTERM, SIGINT)
- Task tracking with configurable timeout
- Subprocess management (SIGTERM → wait → SIGKILL)
- Cleanup callbacks with async support
- Database state persistence
- Resource cleanup (sessions, connections)

**Test Coverage**: 29 unit tests, 91% coverage

**Configuration**:
- `shutdown_timeout`: Grace period in seconds (default: 300)

**Dependencies**: signal, asyncio, subprocess

**When to modify**: Changing shutdown behavior, adding cleanup tasks

---

### 20. agent_helpers.py (47 lines)

**Purpose**: Utility functions for agent operations

**Key Functions**:
```python
def parse_agent_output(output: str) -> dict
    """Parse structured output from agents"""

def validate_agent_response(response: dict) -> bool
    """Validate agent response format"""
```

**Dependencies**: None (pure Python)

**When to modify**: Adding new agent utilities

---

## Test Files (tests/)

### Unit Tests (tests/unit/) - 5,396 lines total

**Purpose**: Fast, isolated tests for individual components

**Test Files**:

1. **test_config.py** (140 lines)
   - Configuration loading
   - Environment variable validation
   - 15 tests

2. **test_asana_client.py** (200 lines)
   - Asana API wrapper methods
   - Retry logic
   - Mock API responses

3. **test_asana_models.py** (160 lines)
   - Pydantic model validation
   - Data serialization

4. **test_crud.py** (1,115 lines) ⭐ COMPREHENSIVE
   - All CRUD operations
   - Error handling
   - Transaction rollback
   - 89 tests

5. **test_formatters.py** (479 lines)
   - Response formatting
   - Long response splitting
   - Markdown generation
   - 42 tests

6. **test_orchestrator.py** (492 lines)
   - Task queue operations
   - Agent pool management
   - Orchestration logic

7. **test_prioritizer.py** (529 lines) ⭐ COMPREHENSIVE
   - Priority scoring
   - Multi-factor algorithm
   - Edge cases
   - 36 tests, 92% coverage

8. **test_shutdown.py** (472 lines) ⭐ COMPREHENSIVE
   - Signal handling
   - Subprocess management
   - Cleanup callbacks
   - 29 tests, 91% coverage

9. **test_simple_executor.py** (409 lines)
   - Claude API calls
   - Prompt generation
   - Response handling
   - 28 tests

**Running Unit Tests**:
```bash
pytest tests/unit/ -v
pytest tests/unit/test_prioritizer.py -v
pytest tests/unit/ --cov=src/aegis --cov-report=html
```

---

### Integration Tests (tests/integration/) - 1,123 lines

**Purpose**: Slower tests with external dependencies

**Test Files**:

1. **test_e2e.py** (1,123 lines) ⭐ COMPREHENSIVE E2E TESTS
   - Full workflow testing
   - Asana API integration
   - Database integration
   - CLI command testing
   - 14 E2E tests

**Test Suites**:
```python
class TestCLIIntegration:
    """Tests CLI commands without Asana"""
    # Config, help, version tests

class TestAsanaIntegration:
    """Tests Asana API operations"""
    # Fetch tasks, projects, comments

class TestDatabaseIntegration:
    """Tests database operations"""
    # CRUD operations, sync

class TestFullWorkflow:
    """Tests complete workflows"""
    # Autonomous execution, orchestration
```

**Running Integration Tests**:
```bash
pytest tests/integration/ -v
pytest tests/integration/test_e2e.py::TestCLIIntegration -v
```

**Documentation**:
- `E2E_TEST_GUIDE.md` - Complete testing guide
- `E2E_STATUS.md` - Current test status
- `TEST_SUMMARY.md` - Test overview
- `QUICK_START.md` - Quick start guide

---

### Test Configuration

**conftest.py** (63 lines):
- Pytest fixtures
- Test database setup
- Mock configurations
- Shared test utilities

**manual_shutdown_test.py** (277 lines):
- Manual shutdown testing
- Signal handling verification
- Interactive testing

---

## Utility Scripts (scripts/) - 1,866 lines total

**Purpose**: Helper scripts for setup, testing, and maintenance

### Setup Scripts

1. **setup_asana.py** (88 lines)
   - Initial Asana project setup
   - Creates portfolio and projects

2. **create_project.py** (131 lines)
   - Create new Asana project
   - Apply section structure

3. **add_project_to_portfolio.py** (58 lines)
   - Add single project to portfolio

4. **add_projects_to_portfolio.py** (89 lines)
   - Batch add projects to portfolio

5. **list_workspace_projects.py** (89 lines)
   - List all workspace projects

### Testing Scripts

6. **populate_tasks.py** (595 lines) ⭐ LARGE
   - Populate test tasks in Asana
   - Create realistic test data

7. **cleanup_test_tasks.py** (186 lines)
   - Clean up test data
   - Remove test tasks

8. **test_prompts.py** (244 lines)
   - Test prompt generation
   - Verify prompt templates

### Utility Scripts

9. **complete_task.py** (151 lines)
   - Manually complete a task
   - Bypass normal workflow

10. **populate_prompt_templates.py** (416 lines)
    - Populate prompt templates
    - Template management

11. **uncomplete_failed_tasks.py** (129 lines)
    - Find failed tasks
    - Move back to Ready to Implement
    - Add explanatory comments

**Running Scripts**:
```bash
python scripts/setup_asana.py
python scripts/populate_tasks.py
python scripts/uncomplete_failed_tasks.py
```

---

## Database Migrations (alembic/)

**Purpose**: Database schema versioning and migrations

**Files**:

1. **env.py** (84 lines)
   - Alembic environment configuration
   - Connection setup
   - Logging configuration

2. **versions/22bba2d16585_initial_schema_system_state_task_.py** (242 lines)
   - Initial schema migration
   - Creates all tables
   - Sets up indexes and foreign keys

**Commands**:
```bash
alembic upgrade head          # Apply all migrations
alembic downgrade -1          # Rollback one migration
alembic revision --autogenerate -m "Description"  # Create new migration
alembic current               # Show current version
alembic history               # Show all migrations
```

---

## Documentation Files

### Primary Documentation (docs/)

1. **OPERATOR_GUIDE.md** - Complete operator guide
2. **SHUTDOWN_HANDLING.md** - Shutdown implementation
3. **PRIORITIZATION.md** - Task prioritization
4. **QUESTION_AUTO_COMPLETE.md** - Question auto-completion
5. **AGENT_COMMAND.md** - Agent command docs

### Design Documents (design/)

1. **PROJECT_OVERVIEW.md** - Project vision
2. **TASK_LIST.md** - Implementation roadmap
3. **DATABASE_SCHEMA.md** - Database design
4. **ORCHESTRATION.md** - Orchestration architecture
5. **AUTONOMOUS_WORK_PATTERN.md** - Autonomous execution

### Implementation Summaries (root)

Over 20 implementation summary documents tracking features:
- E2E_IMPLEMENTATION_SUMMARY.md
- SHUTDOWN_IMPLEMENTATION_SUMMARY.md
- PRIORITIZATION_IMPLEMENTATION_SUMMARY.md
- SIMPLE_EXECUTOR_IMPLEMENTATION_SUMMARY.md
- WEB_DASHBOARD_IMPLEMENTATION.md
- SYNC_IMPLEMENTATION_SUMMARY.md
- etc.

---

## Configuration Files

### Core Configuration

1. **.env** (NOT in git)
   - Secrets and credentials
   - API keys
   - Database URLs

2. **.env.example**
   - Template for .env
   - All required variables documented

3. **.env.test**
   - Test environment configuration

4. **pyproject.toml**
   - Python project configuration
   - Dependencies (managed by uv)
   - Package metadata
   - Build settings

5. **alembic.ini**
   - Alembic configuration
   - Database URL
   - Migration settings

6. **docker-compose.yml**
   - PostgreSQL service
   - Redis service
   - Local development setup

---

## Key Relationships Between Files

### Data Flow

```
User Command (cli.py)
    ↓
AsanaClient (asana/client.py)
    ↓
Database CRUD (database/crud.py)
    ↓
ORM Models (database/models.py)
    ↓
PostgreSQL Database
```

### Orchestration Flow

```
Orchestrator (orchestrator/main.py)
    ↓
Prioritizer (orchestrator/prioritizer.py)
    ↓
AgentClient (orchestrator/agent_client.py)
    ↓
SimpleExecutor (agents/simple_executor.py)
    ↓
Claude API
    ↓
Formatters (agents/formatters.py)
    ↓
AsanaClient (asana/client.py)
```

### Testing Flow

```
Test Runner (pytest)
    ↓
Test Files (tests/unit/, tests/integration/)
    ↓
Fixtures (tests/conftest.py)
    ↓
Source Code (src/aegis/)
```

---

## File Modification Guidelines

### When modifying specific files:

**cli.py** (2,575 lines):
- ✅ Add new CLI commands
- ✅ Change command-line interface
- ❌ Add business logic (move to appropriate module)
- ⚠️ Very large file - consider extracting commands to separate modules

**asana/client.py** (910 lines):
- ✅ Add new Asana API endpoints
- ✅ Change retry logic
- ❌ Add non-Asana functionality
- ⚠️ All methods should be async

**database/crud.py** (988 lines):
- ✅ Add new CRUD operations
- ✅ Add new query patterns
- ❌ Add business logic
- ⚠️ Always use structured logging

**orchestrator/main.py** (1,153 lines):
- ✅ Change orchestration logic
- ✅ Add new execution modes
- ❌ Add agent-specific logic (use agents/)
- ⚠️ Very large file - consider breaking up

**agents/simple_executor.py** (397 lines):
- ✅ Change prompt generation
- ✅ Modify Claude API calls
- ❌ Add orchestration logic
- ⚠️ Keep agent-specific

---

## Common Patterns

### 1. Async/Await Pattern
```python
# All I/O operations use async
async def fetch_data():
    result = await async_operation()
    return result

# Run in main
asyncio.run(fetch_data())
```

### 2. Database Session Pattern
```python
from aegis.database.session import get_db_session

with get_db_session() as session:
    project = create_project(session, **data)
    # Auto-commit on exit
```

### 3. Structured Logging Pattern
```python
import structlog
logger = structlog.get_logger()

logger.info("operation_success", task_id=task_id, count=5)
logger.error("operation_failed", task_id=task_id, error=str(e))
```

### 4. Configuration Access Pattern
```python
from aegis.config import Settings

config = Settings()  # Loads from .env
api_key = config.anthropic_api_key
```

### 5. Error Handling Pattern
```python
try:
    result = await operation()
    logger.info("success", result=result)
    return result
except SpecificException as e:
    logger.error("failed", error=str(e))
    raise
```

---

## Code Statistics by Module

| Module | Files | Lines | Purpose |
|--------|-------|-------|---------|
| cli | 1 | 2,575 | Main CLI interface |
| asana | 3 | 1,048 | Asana API integration |
| database | 5 | 1,694 | Database layer |
| orchestrator | 6 | 3,060 | Task orchestration |
| agents | 5 | 1,497 | AI agents |
| sync | 2 | 298 | Asana sync |
| utils | 2 | 432 | Utilities |
| **Total Source** | **38** | **~11,500** | |
| **Unit Tests** | **10** | **4,996** | |
| **Integration Tests** | **1** | **1,123** | |
| **Scripts** | **13** | **1,866** | |
| **Migrations** | **2** | **326** | |
| **Grand Total** | **57** | **~18,666** | |

---

## Quick Reference

### Largest Files (Top 10)
1. cli.py - 2,575 lines (main CLI)
2. orchestrator/main.py - 1,153 lines (orchestrator)
3. test_e2e.py - 1,123 lines (E2E tests)
4. test_crud.py - 1,115 lines (CRUD tests)
5. database/crud.py - 988 lines (CRUD operations)
6. orchestrator/web.py - 988 lines (web dashboard)
7. asana/client.py - 910 lines (Asana API)
8. populate_tasks.py - 595 lines (test data)
9. test_prioritizer.py - 529 lines (prioritizer tests)
10. test_shutdown.py - 472 lines (shutdown tests)

### Most Critical Files (by importance)
1. ⭐ cli.py - Main entry point
2. ⭐ asana/client.py - Asana API wrapper
3. ⭐ database/models.py - Database schema
4. ⭐ database/crud.py - CRUD operations
5. ⭐ orchestrator/main.py - Orchestration engine
6. ⭐ orchestrator/prioritizer.py - Task prioritization
7. ⭐ orchestrator/web.py - Web dashboard
8. ⭐ agents/simple_executor.py - Claude API agent
9. ⭐ utils/shutdown.py - Graceful shutdown
10. ⭐ config.py - Configuration

### Test Coverage
- **Unit Tests**: 10 files, ~5,000 lines
- **Integration Tests**: 1 file, ~1,100 lines
- **Coverage**: 90%+ for critical modules
- **Total Tests**: 200+ tests

---

## For LLM Assistants

When working on this codebase:

1. **Start with cli.py** (2,575 lines) - understand user-facing commands
2. **Check asana/client.py** (910 lines) - for Asana API operations
3. **Review database/models.py** (347 lines) - for schema understanding
4. **Read orchestrator/main.py** (1,153 lines) - for orchestration flow
5. **Examine agents/simple_executor.py** (397 lines) - for agent execution

**Always**:
- Use structured logging (structlog)
- Follow async/await patterns
- Use type hints
- Write tests for new features
- Update this documentation when making structural changes

**Never**:
- Commit secrets (.env file)
- Skip database migrations
- Ignore graceful shutdown
- Break existing tests

---

**This document is maintained as a comprehensive map of the Aegis codebase for LLM/AI assistant use. Update it when adding new files or significantly changing existing ones.**
