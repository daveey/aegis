#!/usr/bin/env python3
"""Populate Asana projects with initial tasks from the roadmap."""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aegis.config import get_settings
import asana


# Define tasks for Aegis project (Phase 1 development work)
AEGIS_TASKS = [
    # Database Setup (Priority 1 - Needed for everything else)
    {
        "name": "Set up PostgreSQL database",
        "description": """**Goal**: Get PostgreSQL running locally for Aegis state management

**Steps**:
1. Install PostgreSQL locally OR use Docker container
2. Create database named 'aegis'
3. Create user with appropriate permissions
4. Update .env with DATABASE_URL

**Questions**:
- Docker vs local install preference?
- Should we use pgAdmin for management?

**Acceptance Criteria**:
- Can connect to database using psql
- DATABASE_URL in .env works with SQLAlchemy
""",
        "section": "Database Setup",
    },
    {
        "name": "Configure Alembic migrations",
        "description": """**Goal**: Set up Alembic to manage database schema changes

**Steps**:
1. Edit alembic.ini with correct database URL
2. Update alembic/env.py to import our models
3. Create initial migration with all tables
4. Run migration to create schema
5. Verify all tables created

**Dependencies**: Requires PostgreSQL running

**Acceptance Criteria**:
- `alembic upgrade head` creates all tables
- `alembic downgrade base` drops all tables
- Can see migrations in alembic_version table
""",
        "section": "Database Setup",
    },
    {
        "name": "Create database CRUD operations",
        "description": """**Goal**: Implement basic Create/Read/Update/Delete for core models

**Models to implement**:
- Project: create, get_by_gid, get_all, update
- Task: create, get_by_gid, get_by_project, update, mark_complete
- TaskExecution: create, get_by_task, update_status

**Steps**:
1. Create src/aegis/database/crud.py
2. Implement CRUD functions using session context manager
3. Add error handling for common cases (not found, duplicate)
4. Write unit tests for each operation

**Acceptance Criteria**:
- Can create/read/update records for each model
- Tests pass with 90%+ coverage
""",
        "section": "Database Setup",
    },
    {
        "name": "Build Asana sync utility",
        "description": """**Goal**: Sync Asana projects and tasks into local database

**Features**:
1. Fetch all projects from portfolio
2. Store/update projects in database
3. Fetch tasks for each project
4. Store/update tasks in database
5. Handle incremental updates (only changed tasks)

**Steps**:
1. Create src/aegis/sync/asana_sync.py
2. Implement sync_projects() - portfolio → DB
3. Implement sync_tasks(project_id) - tasks → DB
4. Add CLI command: `aegis sync`
5. Track last_synced_at timestamps

**Questions**:
- Should we sync on a schedule or on-demand only?
- How often to sync (every 30s? 1 min? 5 min?)?

**Acceptance Criteria**:
- Can run `aegis sync` and see projects/tasks in DB
- Re-running sync updates existing records (idempotent)
- Tracks last sync time
""",
        "section": "Database Setup",
    },
    {
        "name": "Create database seed script",
        "description": """**Goal**: Seed database with initial data for testing

**Data to seed**:
1. Existing projects (Triptic, Aegis) from Asana
2. Sample tasks for testing
3. System state initialization
4. Sample prompt templates

**Steps**:
1. Create scripts/seed_database.py
2. Fetch real data from Asana (Triptic, Aegis projects)
3. Insert into database
4. Add some test tasks
5. Initialize system_state table

**Acceptance Criteria**:
- `python scripts/seed_database.py` populates empty DB
- Can query for Triptic and Aegis projects
- System state table has one row
""",
        "section": "Database Setup",
    },
    {
        "name": "Write database integration tests",
        "description": """**Goal**: Comprehensive tests for database layer

**Test coverage**:
1. Model relationships (project → tasks)
2. CRUD operations
3. Cascade deletes work correctly
4. Unique constraints enforced
5. Session management (commit/rollback)

**Steps**:
1. Create tests/integration/test_database.py
2. Use in-memory SQLite for fast tests OR test DB
3. Test each model's CRUD operations
4. Test relationships and joins
5. Test transaction handling

**Acceptance Criteria**:
- All tests pass
- 90%+ code coverage for database module
""",
        "section": "Database Setup",
    },
    # Agent Executor (Priority 2 - Core functionality)
    {
        "name": "Design base Agent class",
        "description": """**Goal**: Create abstract base class for all agent types

**Requirements**:
1. Common interface for all agents
2. Lifecycle management (start, stop, status)
3. Task execution method
4. Event logging integration
5. Performance tracking

**Design considerations**:
- Should agents be stateful or stateless?
- How to handle long-running tasks?
- Thread safety requirements?

**Steps**:
1. Create src/aegis/agents/base.py
2. Define Agent abstract base class
3. Add common methods: execute_task, log_event, update_metrics
4. Add agent registry pattern
5. Document usage with examples

**Acceptance Criteria**:
- Can subclass Agent to create specialized agents
- Base class handles all logging and metrics
- Clear documentation with examples
""",
        "section": "Agent Framework",
    },
    {
        "name": "Implement Anthropic API client wrapper",
        "description": """**Goal**: Clean wrapper around Anthropic SDK for agent use

**Features**:
1. Async API calls
2. Retry logic with exponential backoff
3. Token counting and cost tracking
4. Streaming response support
5. Error handling

**Steps**:
1. Create src/aegis/agents/llm_client.py
2. Implement ClaudeClient class
3. Add methods: complete, stream, count_tokens
4. Track usage metrics (tokens, cost)
5. Write unit tests with mocked API

**Questions**:
- Should we support multiple models (Sonnet, Opus, Haiku)?
- Cache responses for identical prompts?

**Acceptance Criteria**:
- Can call Claude API and get response
- Tracks token usage and cost
- Handles rate limits gracefully
- Tests pass with mocked API
""",
        "section": "Agent Framework",
    },
    {
        "name": "Build SimpleExecutor agent",
        "description": """**Goal**: First working agent that processes tasks

**Functionality**:
1. Accept Asana task as input
2. Generate prompt from task description
3. Call Claude API
4. Post response as Asana comment
5. Log execution to database

**Steps**:
1. Create src/aegis/agents/simple_executor.py
2. Subclass from Agent base
3. Implement execute_task() method
4. Add prompt template for task processing
5. Integrate with TaskExecution model

**Flow**:
Task → Parse → Generate Prompt → Claude API → Format Response → Post Comment → Log

**Acceptance Criteria**:
- Can process a real Asana task end-to-end
- Response posted as comment
- Execution logged to database
""",
        "section": "Agent Framework",
    },
    {
        "name": "Create prompt templates for SimpleExecutor",
        "description": """**Goal**: Design effective prompts for task processing

**Templates needed**:
1. System prompt: Define agent role and capabilities
2. Task analysis: Understand what's being asked
3. Code task: Handle software development requests
4. Research task: Handle information gathering
5. Question/clarification: When task is unclear

**Steps**:
1. Design system prompt (agent personality, guidelines)
2. Create task type classifier prompt
3. Design specialized prompts for each task type
4. Store in prompt_templates table
5. Add template variables for dynamic content

**Questions**:
- Should we include Asana project context in prompts?
- How much task history to include?

**Acceptance Criteria**:
- Prompts stored in database
- Can load and render templates
- Templates produce quality responses
""",
        "section": "Agent Framework",
    },
    {
        "name": "Implement task response formatter",
        "description": """**Goal**: Format agent output for Asana comments

**Features**:
1. Markdown formatting
2. Code blocks with syntax highlighting
3. Multi-part responses (if too long)
4. Status indicators (in progress, blocked, complete)
5. Error formatting

**Steps**:
1. Create src/aegis/agents/formatters.py
2. Implement format_response() function
3. Handle long responses (split if > 65k chars)
4. Add markdown enhancement (lists, headers, code blocks)
5. Add status badges

**Acceptance Criteria**:
- Responses render nicely in Asana
- Code blocks have proper syntax
- Long responses split appropriately
""",
        "section": "Agent Framework",
    },
    # Orchestration (Priority 3 - Bringing it together)
    {
        "name": "Design orchestration loop architecture",
        "description": """**Goal**: Plan the main event loop that coordinates everything

**Key decisions**:
1. Polling vs webhooks (start with polling)
2. Task queue architecture
3. Error handling and recovery
4. Graceful shutdown
5. Multi-task concurrency

**Architecture questions**:
- Use asyncio event loop?
- How to prioritize tasks?
- Handle tasks that depend on other tasks?
- Agent pool size and scaling strategy?

**Deliverable**:
- Design document in design/ORCHESTRATION.md
- Sequence diagrams for main flows
- Error handling strategy

**Acceptance Criteria**:
- Clear architecture documented
- Reviewed and approved design
""",
        "section": "Orchestration",
    },
    {
        "name": "Build basic orchestrator",
        "description": """**Goal**: Implement main orchestration loop

**Functionality**:
1. Poll Asana for new/updated tasks
2. Identify tasks assigned to Aegis
3. Queue tasks for processing
4. Dispatch to available agents
5. Handle completion/errors
6. Update system state

**Steps**:
1. Create src/aegis/orchestrator/main.py
2. Implement Orchestrator class
3. Add poll loop with configurable interval
4. Add task queue (priority queue)
5. Add agent pool management
6. Integrate with database for state

**Acceptance Criteria**:
- Can start orchestrator with `aegis start`
- Picks up new tasks automatically
- Processes tasks and posts results
- Handles errors gracefully
""",
        "section": "Orchestration",
    },
    {
        "name": "Implement task prioritization",
        "description": """**Goal**: Intelligent task ordering

**Priority factors**:
1. Due dates (urgent tasks first)
2. Task dependencies (parents before children)
3. User-assigned priority (if in custom fields)
4. Project importance
5. Task age (don't starve old tasks)

**Steps**:
1. Create src/aegis/orchestrator/prioritizer.py
2. Implement scoring algorithm
3. Consider multiple factors
4. Add configuration for weights
5. Test with various scenarios

**Acceptance Criteria**:
- Urgent tasks processed first
- Dependencies respected
- Fair scheduling (no starvation)
""",
        "section": "Orchestration",
    },
    {
        "name": "Add graceful shutdown handling",
        "description": """**Goal**: Clean shutdown without losing work

**Requirements**:
1. Catch SIGTERM/SIGINT signals
2. Stop accepting new tasks
3. Wait for in-progress tasks to complete
4. Save state to database
5. Clean up resources

**Steps**:
1. Add signal handlers
2. Implement shutdown sequence
3. Add timeout (max wait time)
4. Update system_state on shutdown
5. Test shutdown scenarios

**Acceptance Criteria**:
- Ctrl+C shuts down cleanly
- In-progress tasks complete
- State saved correctly
- No database connections left open
""",
        "section": "Orchestration",
    },
    # Testing & Documentation (Priority 4 - Quality)
    {
        "name": "Create end-to-end integration test",
        "description": """**Goal**: Test complete flow from Asana to response

**Test flow**:
1. Create test task in Asana
2. Start orchestrator
3. Verify task picked up
4. Verify agent processes task
5. Verify response posted
6. Verify execution logged

**Steps**:
1. Create tests/integration/test_e2e.py
2. Set up test Asana project
3. Use real APIs (or well-mocked)
4. Test happy path
5. Test error cases
6. Clean up after tests

**Acceptance Criteria**:
- Complete flow works end-to-end
- Test is repeatable
- Can run in CI/CD pipeline
""",
        "section": "Testing",
    },
    {
        "name": "Write operator documentation",
        "description": """**Goal**: Guide for running and operating Aegis

**Documentation needed**:
1. Installation guide
2. Configuration reference
3. Running the orchestrator
4. Monitoring and logs
5. Troubleshooting common issues

**Steps**:
1. Create docs/OPERATOR_GUIDE.md
2. Document setup process
3. Document configuration options
4. Add monitoring guide
5. Add troubleshooting section

**Acceptance Criteria**:
- Can follow docs to set up from scratch
- All config options documented
- Common issues covered
""",
        "section": "Documentation",
    },
]

# Tasks for Triptic project (actual work on the Triptic codebase)
TRIPTIC_TASKS = [
    {
        "name": "Set up development environment",
        "description": """**Goal**: Get Triptic codebase running locally

**Steps**:
1. Review README.md in ~/code/eo
2. Install dependencies (npm install)
3. Set up environment variables
4. Run development server
5. Verify app loads

**Questions**:
- What does the Triptic app do?
- Are there any environment variables needed?
- Database requirements?

**Acceptance Criteria**:
- App runs locally without errors
- Can view in browser
""",
        "section": "Setup",
    },
    {
        "name": "Document Triptic codebase structure",
        "description": """**Goal**: Understand the codebase architecture

**Deliverables**:
1. High-level architecture diagram
2. Key components and their responsibilities
3. Data flow documentation
4. API endpoints (if applicable)
5. Build/deploy process

**Steps**:
1. Explore src/ directory
2. Identify main components
3. Document in docs/ARCHITECTURE.md
4. Note any technical debt or issues

**Acceptance Criteria**:
- Architecture clearly documented
- Easy for others to understand codebase
""",
        "section": "Documentation",
    },
]


async def create_tasks_for_project(project_gid: str, tasks: list[dict]) -> None:
    """Create tasks in an Asana project.

    Args:
        project_gid: The project to create tasks in
        tasks: List of task definitions
    """
    settings = get_settings()

    # Configure API client
    configuration = asana.Configuration()
    configuration.access_token = settings.asana_access_token
    api_client = asana.ApiClient(configuration)
    tasks_api = asana.TasksApi(api_client)

    print(f"\nCreating {len(tasks)} tasks in project {project_gid}...")

    created_count = 0
    failed_count = 0

    for task_def in tasks:
        try:
            # Create task
            task_data = {
                "data": {
                    "name": task_def["name"],
                    "notes": task_def["description"],
                    "projects": [project_gid],
                }
            }

            result = await asyncio.to_thread(
                tasks_api.create_task, task_data, {"opt_fields": "name,gid,permalink_url"}
            )

            print(f"✓ Created: {task_def['name']}")
            print(f"  GID: {result['gid']}")
            created_count += 1

        except Exception as e:
            print(f"✗ Failed: {task_def['name']}")
            print(f"  Error: {str(e)[:100]}")
            failed_count += 1

    print(f"\nSummary:")
    print(f"  Created: {created_count}")
    print(f"  Failed: {failed_count}")
    print(f"  Total: {len(tasks)}")


async def main() -> None:
    """Main entry point."""
    settings = get_settings()

    # Get project GIDs
    aegis_project_gid = "1212085431574340"  # From earlier creation
    triptic_project_gid = "1212085075370316"  # From earlier creation

    print("="*60)
    print("Populating Asana Projects with Tasks")
    print("="*60)

    # Create Aegis tasks
    print(f"\n{'='*60}")
    print(f"Aegis Project Tasks (Development)")
    print(f"{'='*60}")
    await create_tasks_for_project(aegis_project_gid, AEGIS_TASKS)

    # Create Triptic tasks
    print(f"\n{'='*60}")
    print(f"Triptic Project Tasks (Application)")
    print(f"{'='*60}")
    await create_tasks_for_project(triptic_project_gid, TRIPTIC_TASKS)

    print(f"\n{'='*60}")
    print("All Done!")
    print(f"{'='*60}")
    print(f"\nView tasks:")
    print(f"  Aegis: https://app.asana.com/0/1212085431574340")
    print(f"  Triptic: https://app.asana.com/0/1212085075370316")


if __name__ == "__main__":
    asyncio.run(main())
