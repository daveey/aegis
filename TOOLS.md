# Aegis Tools

This document describes the tools available in Aegis that can be used by Claude Code or other automation systems.

## aegis do [project]

Execute the first incomplete task from an Asana project using Claude CLI.

### Usage

```bash
aegis do [project_name]
```

### Arguments

- `project_name` - Name of the Asana project (case-insensitive). Project must be in the Aegis portfolio.

### Examples

```bash
# Execute first task in Aegis project
aegis do Aegis

# Execute first task in Triptic project
aegis do Triptic
```

### Behavior

1. **Finds Project**: Searches Aegis portfolio for matching project
2. **Extracts Code Path**: Reads code location from project notes
3. **Fetches First Task**: Gets first incomplete task from project
4. **Executes Task**: Runs Claude CLI interactively with task context in project directory
5. **Shows Result**: Displays exit code when complete

### Output

- **Console**: Real-time Claude CLI output during execution
- **Exit Status**: Success or failure indicator after completion

### Error Handling

The command is designed to be robust:

- **API Retry Logic**: Automatically retries Asana API calls (3 attempts with exponential backoff)
- **Graceful Degradation**: Reports errors clearly without crashing
- **Fatal Errors**: Exits with code 1 only for unrecoverable errors (Claude CLI not found, project not found)

### Exit Codes

- `0` - Success (task executed and completed)
- `1` - Fatal error (Claude CLI not found, project not found, or critical failure)

### Requirements

- Claude CLI must be installed and available in PATH
- Valid Asana API token in `.env`
- Project must exist in Aegis portfolio
- Project must have at least one incomplete task

### Flags Used with Claude CLI

The command automatically uses these flags:
- `--dangerously-skip-permissions` - Bypass permission prompts for automation

### Integration with Claude Code

This command can be invoked by Claude Code using the Bash tool:

```python
# From within Claude Code
result = subprocess.run(["aegis", "do", "Aegis"])
```

The command is designed to be called programmatically and handles all errors gracefully.

## aegis work-on [project]

Autonomous project work - assess state, identify blockers, ask questions, and execute ready tasks.

### Usage

```bash
aegis work-on [project_name] [options]
```

### Arguments

- `project_name` - Name of the Asana project (case-insensitive). Project must be in the Aegis portfolio.

### Options

- `--max-tasks N` - Maximum number of tasks to execute in one session (default: 5)
- `--dry-run` - Show what would be done without executing tasks

### Examples

```bash
# Autonomous work on Aegis project
aegis work-on Aegis

# Work on up to 3 tasks
aegis work-on Aegis --max-tasks 3

# See what would be done without executing
aegis work-on Aegis --dry-run
```

### Behavior

1. **Fetch All Tasks**: Gets all incomplete unassigned tasks from the project
2. **Assess State**: Analyzes tasks for dependencies and blockers
3. **Identify Blockers**: Detects tasks that can't be executed yet (e.g., missing PostgreSQL)
4. **Create Questions**: Automatically creates question tasks assigned to user for blockers
5. **Select Ready Tasks**: Identifies tasks with no blockers
6. **Execute Tasks**: Runs Claude CLI on ready tasks (up to max-tasks limit)
7. **Report Summary**: Shows what was completed, blocked, and questions created

### Blocker Detection

The command detects blockers through:

- **Keyword Analysis**: Looks for "Dependencies:", "Depends on:", "Blocked by:" in task descriptions
- **Environment Checks**: Verifies required services (PostgreSQL, Redis, etc.) are running
- **Prerequisite Detection**: Identifies foundation tasks that should be done first

### Question Task Format

When blockers are found, the command creates question tasks with:
- Clear description of the blocker
- Multiple options to resolve
- Recommendation from Claude
- Assigned to portfolio owner (you)

### Output

```
Analyzing Aegis project...
✓ Found 17 incomplete unassigned tasks

Assessing project state...
⚠ Blocked tasks: 5
  • Set up PostgreSQL database
    Reason: Requires PostgreSQL (container not running)
  • Configure Alembic migrations
    Reason: Has explicit dependencies in description

? Questions to create: 1
  • PostgreSQL Setup

✓ Ready tasks: 12
  • Design base Agent class
  • Implement Anthropic API client wrapper
  • Create prompt templates for SimpleExecutor
  • Build SimpleExecutor agent
  • Implement task response formatter

Creating question tasks...
  ✓ Created: Question: PostgreSQL Setup (GID: 1234567890)

Executing 5 ready task(s)...

[1/5] Design base Agent class
  Working directory: /Users/daveey/code/aegis
  ✓ Completed

[2/5] Implement Anthropic API client wrapper
  Working directory: /Users/daveey/code/aegis
  ✓ Completed

...

============================================================
Session Summary
  ✓ Completed: 5 tasks
  ⚠ Blocked: 5 tasks
  ? Questions: 1 created

Log: /Users/daveey/code/aegis/logs/aegis.log
============================================================
```

### Comparison to `aegis do`

| Feature | `do` | `work-on` |
|---------|------|-----------|
| Task selection | First task only | All ready tasks |
| Blocker detection | None | Yes |
| Question creation | No | Yes, auto-assigned |
| Multi-task execution | No | Yes (up to max-tasks) |
| Dependency awareness | No | Yes |
| Session summary | Basic | Comprehensive |
| Use case | Single task execution | Autonomous project work |

### When to Use

**Use `aegis do`** when:
- You want to execute a specific task (the first one)
- Quick, simple execution needed
- No need for assessment

**Use `aegis work-on`** when:
- You want to make progress on a project autonomously
- Tasks may have dependencies or blockers
- You want Claude to ask questions when stuck
- You want to execute multiple tasks in one session

### Requirements

- Claude CLI must be installed and available in PATH
- Valid Asana API token in `.env`
- Project must exist in Aegis portfolio
- Docker (optional, for checking PostgreSQL status)

### Error Handling

The command is designed to be robust:

- **API Retry Logic**: Automatically retries Asana API calls
- **Task Timeouts**: Each task has 5-minute timeout
- **Graceful Failures**: Continues with other tasks if one fails
- **Clear Reporting**: Summary shows successes, failures, and blockers

### Integration with Claude Code

This command can be invoked by Claude Code:

```python
# From within Claude Code
result = subprocess.run(["aegis", "work-on", "Aegis", "--max-tasks", "3"])
```

### Design Documentation

See `design/AUTONOMOUS_WORK_PATTERN.md` for detailed architecture and design decisions.

## aegis plan [project]

Review task list and ensure the "Ready to Implement" section has the target number of tasks (default: 5).

### Usage

```bash
aegis plan [project_name] [options]
```

### Arguments

- `project_name` - Name of the Asana project (case-insensitive). Project must be in the Aegis portfolio.

### Options

- `--target N` - Target number of tasks in "Ready to Implement" section (default: 5)
- `--dry-run` - Show what would be done without executing

### Examples

```bash
# Ensure 5 tasks are ready to implement in Aegis project
aegis plan Aegis

# Ensure 10 tasks are ready
aegis plan Aegis --target 10

# Preview what would be done without making changes
aegis plan Aegis --dry-run
```

### Behavior

1. **Analyze Sections**: Fetches tasks from all sections in the project
2. **Check Ready Count**: Counts incomplete tasks in "Ready to Implement" section
3. **If Target Met**:
   - Asks Claude to review tasks for consolidation opportunities
   - Identifies duplicates or tasks that could be merged
   - Suggests improved descriptions or priority order
4. **If Below Target**:
   - Identifies candidate tasks from other sections (prioritizes: Ideas → Waiting for Response → In Progress)
   - Asks Claude to select and prioritize which tasks to move
   - Moves selected tasks to "Ready to Implement"

### Claude Integration

The command uses Claude CLI to:
- **Select tasks intelligently**: Considers task dependencies, clarity, and value
- **Avoid duplicates**: Checks against existing ready tasks
- **Provide reasoning**: Explains why each task was selected
- **Consolidate when needed**: Suggests merging similar tasks when target is already met

### Output Example

```
Planning tasks for: Aegis

Target: 5 tasks in 'Ready to Implement'

Analyzing sections...
  Waiting for Response: 2 incomplete tasks
  Ready to Implement: 2 incomplete tasks
  In Progress: 3 incomplete tasks
  Implemented: 15 incomplete tasks
  Answered: 0 incomplete tasks
  Ideas: 8 incomplete tasks

Current state: 2 tasks in 'Ready to Implement'
Need to move 3 tasks to 'Ready to Implement'

Asking Claude to select and prioritize tasks...

Consulting Claude for task selection...

✓ Claude selected 3 tasks

  Moving: Implement graceful shutdown handling
    From: Ideas
    ✓ Moved to Ready to Implement

  Moving: Add task prioritization algorithm
    From: Ideas
    ✓ Moved to Ready to Implement

  Moving: Create integration test suite
    From: Ideas
    ✓ Moved to Ready to Implement

✓ Successfully moved 3 tasks!
'Ready to Implement' now has 5 tasks
```

### Task Selection Priority

When moving tasks to "Ready to Implement", the command:

1. **Prefers unblocked tasks**: Tasks without dependencies
2. **Prioritizes sections**: Ideas > Waiting for Response > In Progress (unassigned)
3. **Skips assigned tasks**: Won't move tasks actively being worked on
4. **Uses Claude judgment**: Final selection uses Claude's understanding of task importance

### Consolidation Mode

When target is already met, Claude will:

```
✓ Already have 7 tasks ready (target: 5)

Asking Claude to review tasks for consolidation...

Claude's Analysis:

I've reviewed the 7 tasks in "Ready to Implement". Here are my recommendations:

**Duplicates/Similar Tasks:**
1. "Add logging to orchestrator" and "Implement structured logging" could be consolidated
   - These both involve adding logging functionality
   - Recommend: Merge into "Implement structured logging for orchestrator"

2. "Create unit tests" and "Add test coverage" are overlapping
   - Recommend: Consolidate into "Increase test coverage with unit tests"

**Unclear Tasks:**
- "Fix bug in client" needs more specific description
- "Update docs" should specify which documentation

**Suggested Priority Order:**
1. Implement structured logging for orchestrator (foundation)
2. Add graceful shutdown handling (critical feature)
3. Increase test coverage with unit tests (quality)
4. ...
```

### Requirements

- Claude CLI must be installed and available in PATH
- Valid Asana API token in `.env`
- Project must exist in Aegis portfolio
- Project must have standard sections (run `aegis organize` first)

### When to Use

**Use `aegis plan`** when:
- Starting work on a project and want to ensure tasks are ready
- Project backlog needs organizing
- Want to maintain a healthy "Ready to Implement" queue
- Need to consolidate or clean up duplicate tasks

**Run regularly** to:
- Keep project organized
- Ensure there's always work ready to do
- Identify tasks that need clarification
- Prevent the backlog from becoming stale

### Comparison to Other Commands

| Feature | `plan` | `work-on` | `organize` |
|---------|--------|-----------|------------|
| Reviews tasks | Yes | Yes | No |
| Moves tasks between sections | Yes | No | No |
| Executes tasks | No | Yes | No |
| Creates sections | No | No | Yes |
| Uses Claude intelligence | Yes | Yes | No |
| Consolidates tasks | Yes | No | No |

### Integration with Claude Code

This command can be invoked by Claude Code:

```python
# From within Claude Code
result = subprocess.run(["aegis", "plan", "Aegis", "--target", "5"])
```

### Error Handling

The command is designed to be robust:

- **API Retry Logic**: Automatically retries Asana API calls
- **Fallback Selection**: If Claude's JSON parsing fails, uses automatic selection
- **Clear Reporting**: Shows what was moved and from which section
- **Dry-run Mode**: Test without making changes
## aegis start [project]

Start the Aegis orchestrator for continuous task monitoring and execution.

### Usage

```bash
aegis start [project_name]
```

### Arguments

- `project_name` - Name of the Asana project (case-insensitive), or project GID, or Asana URL

### Examples

```bash
# Start orchestrator for Aegis project
aegis start Aegis

# Start with project GID
aegis start 1212085431574340

# Start with Asana URL
aegis start https://app.asana.com/0/1212085431574340
```

### Behavior

The orchestrator runs continuously and:

1. **Polls Asana**: Fetches incomplete, unassigned tasks every N seconds (default: 30)
2. **Prioritizes Tasks**: Uses multi-factor scoring (due date, dependencies, user priority, project, age)
3. **Manages Queue**: Maintains priority queue of tasks to execute
4. **Dispatches Tasks**: Assigns tasks to available agent slots (max concurrent configurable)
5. **Monitors Execution**: Tracks task execution via subprocess
6. **Updates Display**: Shows real-time status in full-screen console or web dashboard
7. **Posts Results**: Adds comments to Asana tasks with execution results

### Features

- **Live Console Display**: Full-screen rich console with task status
- **Web Dashboard**: Real-time web interface at http://127.0.0.1:8000
  - Shows orchestrator status, statistics, and active agents
  - Displays task logs in real-time
  - WebSocket-based updates
- **Graceful Shutdown**: Handles SIGTERM/SIGINT, waits for tasks to complete
- **Database Logging**: Records all executions in PostgreSQL
- **Concurrent Execution**: Configurable max concurrent tasks (default: 5)

### Configuration

Environment variables (set in `.env`):

```bash
POLL_INTERVAL_SECONDS=30        # How often to check for new tasks
MAX_CONCURRENT_TASKS=5           # Maximum parallel executions
EXECUTION_MODE=simple_executor   # Agent execution mode
SHUTDOWN_TIMEOUT=300             # Shutdown grace period (seconds)
```

### Output

```
Starting Aegis Orchestrator...
Resolving project 'Aegis'...
✓ Monitoring project: Aegis (GID: 1212085431574340)

Configuration:
  Project: Aegis
  Project GID: 1212085431574340
  Poll Interval: 30s
  Max Concurrent Tasks: 3
  Shutdown Timeout: 300s

✓ Orchestrator initialized
Press Ctrl+C to stop gracefully

✓ Orchestrator started (PID: 12345)
Logs: logs/orchestrator_12345.log
🌐 Web Dashboard: http://127.0.0.1:8000
Press Ctrl+C to stop gracefully
```

### Stopping the Orchestrator

- Press `Ctrl+C` once to initiate graceful shutdown
- Orchestrator will wait for active tasks to complete (up to shutdown timeout)
- Press `Ctrl+C` again to force immediate shutdown

### Web Dashboard

Access at http://127.0.0.1:8000 to see:
- Orchestrator status (running/stopped)
- Statistics (dispatched, completed, failed tasks)
- Active agents with real-time log streaming
- Task execution duration

### Requirements

- PostgreSQL database running (tables created via `alembic upgrade head`)
- Valid Asana API token in `.env`
- Project must exist in Aegis portfolio

### When to Use

Use `aegis start` when you want:
- **Continuous Monitoring**: Automatically pick up new tasks as they're created
- **Unattended Execution**: Run the orchestrator in the background
- **Multiple Tasks**: Process tasks continuously without manual intervention
- **Web Monitoring**: View status and logs via web dashboard

Compare to:
- `aegis do`: Single task execution, exits after completion
- `aegis work-on`: Multi-task execution, exits after max tasks or no more ready tasks

### Error Handling

- **API Failures**: Retries with exponential backoff
- **Database Issues**: Logs errors but continues polling
- **Task Failures**: Logs to database, posts error to Asana, continues with next task
- **Shutdown**: Gracefully terminates subprocesses, cleans up resources

---

## aegis sync

Synchronize Asana projects and tasks into the local PostgreSQL database.

### Usage

```bash
aegis sync [options]
```

### Options

- `--projects-only` - Only sync projects, skip tasks (faster)
- `--console / --no-console` - Use rich console formatting (default: true)

### Examples

```bash
# Sync all projects and their tasks
aegis sync

# Sync only projects, skip tasks
aegis sync --projects-only
```

### Behavior

1. **Fetch Projects**: Gets all projects from configured portfolio
2. **Sync to Database**: Creates or updates project records in `projects` table
3. **Fetch Tasks**: For each project, gets all tasks (if not --projects-only)
4. **Sync Tasks**: Creates or updates task records in `tasks` table
5. **Update Timestamps**: Records `last_synced_at` for tracking

### What Gets Synced

**Projects**:
- Asana GID, name, notes
- Portfolio GID, workspace GID
- Archived status
- Permalink URL

**Tasks**:
- Asana GID, name, description, HTML notes
- Completion status and timestamp
- Due dates (due_on, due_at)
- Assignee information
- Parent task relationships
- Subtask count
- Tags and custom fields
- Modified timestamp

### Database Tables

Creates/updates records in:
- `projects` - Asana projects
- `tasks` - Asana tasks
- `system_state` - Last sync timestamps

### Output

```
Syncing Asana projects and tasks...

✓ Portfolio: 1234567890
✓ Workspace: 0987654321

Fetching projects from portfolio...
✓ Found 5 projects

Syncing projects to database...
  ✓ Aegis
  ✓ Triptic
  ✓ Metta
  ✓ Agents
  ✓ Archive

Syncing tasks for each project...

[1/5] Aegis
  Fetching tasks...
  ✓ Found 47 tasks
  Syncing to database...
  ✓ Created 12 new tasks
  ✓ Updated 35 existing tasks

[2/5] Triptic
  Fetching tasks...
  ✓ Found 23 tasks
  ...

✓ Sync complete!
  Projects: 5 synced
  Tasks: 142 total (45 new, 97 updated)
```

### Idempotency

The sync command is idempotent:
- Re-running will update existing records
- Uses Asana GID as unique identifier
- Safe to run multiple times
- No duplicates created

### When to Use

- **Initial Setup**: First time setup to populate database
- **Manual Refresh**: After making changes in Asana outside of Aegis
- **Scheduled Updates**: Run periodically via cron to keep database fresh
- **Data Analysis**: Populate database for reporting or analytics

### Performance

- **Projects Only**: ~2-5 seconds for 5-10 projects
- **Full Sync**: Depends on number of tasks (500 tasks ≈ 30-60 seconds)
- **Incremental**: Uses `last_synced_at` to optimize future syncs

### Requirements

- Valid Asana API token in `.env`
- PostgreSQL database configured and migrations run
- Portfolio GID in configuration

---

## aegis test-claude

Test Claude API connection.

### Usage

```bash
aegis test-claude
```

### Behavior

Sends a simple test message to Claude API to verify:
- API key is valid
- Model is accessible
- Connection works

### Output

```
Testing Claude API connection...

✓ Claude API connection successful!
  Model: claude-sonnet-4-5-20250929
  Response: [test response text]
```

### Requirements

- Valid Anthropic API key in `.env` (ANTHROPIC_API_KEY)
- Internet connection

### When to Use

- **Initial Setup**: Verify API credentials are correct
- **Troubleshooting**: Check if API issues are causing problems
- **Configuration**: Confirm model name is valid

---

## aegis create-agents-project

Create the Agents project in the portfolio for agent definitions.

### Usage

```bash
aegis create-agents-project [options]
```

### Options

- `--name TEXT` - Name of the Agents project (default: "Agents")
- `--console / --no-console` - Use rich console formatting (default: true)

### Examples

```bash
# Create Agents project with default name
aegis create-agents-project

# Create with custom name
aegis create-agents-project --name "My Agents"
```

### Behavior

1. **Check Existing**: Looks for project with specified name in portfolio
2. **Create Project**: Creates new project if not found
3. **Setup Structure**: Adds project description and sections
4. **Add to Portfolio**: Ensures project is in the configured portfolio

### Project Purpose

The Agents project is used by `aegis process-agent-mentions` to:
- Define agent types (each task = one agent)
- Store agent prompts/instructions in task notes
- Configure agent behavior

### Usage Pattern

After creating the Agents project:

1. Create tasks in the project, one per agent type
2. Task name = agent name (e.g., "code-reviewer", "test-writer")
3. Task notes = agent's system prompt/instructions
4. Use `@agent-name` in other project tasks to invoke

### Output

```
Creating Agents project...

✓ Project created: Agents (GID: 1234567890)
✓ Added to portfolio
✓ Project structure configured

You can now add agent definitions as tasks in this project.
```

### Requirements

- Valid Asana API token in `.env`
- Portfolio GID in configuration

---

## aegis process-agent-mentions [project]

Monitor a project for @-mentions of agents and respond.

### Usage

```bash
aegis process-agent-mentions [project_name] [options]
```

### Arguments

- `project_name` - Name of the project to monitor

### Options

- `--agents-project TEXT` - Name of the Agents project (default: "Agents")
- `--poll-interval INTEGER` - How often to check for mentions in seconds (default: 60)
- `--once` - Process mentions once and exit (don't poll)
- `--timeout INTEGER` - Timeout for agent response generation in seconds (default: 300)
- `--console / --no-console` - Use rich console formatting (default: true)

### Examples

```bash
# Monitor Aegis project for agent mentions
aegis process-agent-mentions Aegis

# Check once and exit
aegis process-agent-mentions Aegis --once

# Custom poll interval
aegis process-agent-mentions Aegis --poll-interval 30
```

### Behavior

1. **Load Agents**: Fetches agent definitions from Agents project
   - Each task in Agents project = one agent
   - Task name = agent name
   - Task notes = agent's system prompt
2. **Monitor Comments**: Checks tasks and comments in specified project
3. **Detect Mentions**: Looks for `@agent-name` patterns
4. **Generate Response**: Uses Claude API with agent's prompt to generate response
5. **Post Comment**: Adds agent's response as a comment
6. **React**: Adds emoji reaction to the mention
7. **Repeat**: Continues polling (unless --once flag)

### Agent Definition Format

In the Agents project, create tasks like:

```
Task: code-reviewer

Notes:
You are a code reviewer. When mentioned, review the code changes
discussed in the task and provide feedback on:
- Code quality
- Potential bugs
- Performance concerns
- Best practices
```

### Usage Pattern

In any monitored project:

```
Task: Fix authentication bug

Description:
User login is failing intermittently.

@code-reviewer can you review my fix in commit abc123?
```

The agent-mention processor will:
1. Detect the @code-reviewer mention
2. Load code-reviewer agent's prompt
3. Call Claude API with the prompt + task context
4. Post the response as a comment
5. React to the original mention with ✅

### Output

```
Starting agent mention processor...

✓ Loaded 3 agents from project: Agents
  - code-reviewer
  - test-writer
  - documentation-helper

Monitoring project: Aegis
Poll interval: 60 seconds

Checking for mentions...
  ✓ Found 1 new mention

Processing mention: @code-reviewer in task "Fix auth bug"
  Generating response...
  ✓ Response posted (GID: 1234567890)
  ✓ Reacted to mention

Checking for mentions...
  (No new mentions)
...
```

### Requirements

- Valid Asana API token in `.env`
- Valid Anthropic API key in `.env`
- Agents project must exist (create with `aegis create-agents-project`)
- Agent definitions must be created as tasks in Agents project

### When to Use

- **Collaborative Projects**: Multiple people working, want agent assistance
- **Code Review**: Automated code review on demand
- **Documentation**: Generate docs when @documentation-helper is mentioned
- **Custom Workflows**: Define custom agent behaviors for team needs

### Comparison

| Feature | `process-agent-mentions` | `do` | `work-on` |
|---------|-------------------------|------|-----------|
| Trigger | @-mentions | Manual | Automatic |
| Response | Comment reply | Task execution | Multi-task execution |
| Continuous | Yes (polling) | No | No |
| Custom Agents | Yes | No | No |
| Use Case | Collaboration | Direct execution | Autonomous work |

---
