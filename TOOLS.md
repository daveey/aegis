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
