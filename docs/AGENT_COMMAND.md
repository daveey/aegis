# `aegis agent` Command Documentation

**Status**: ✅ Production Ready
**Version**: 1.0.0
**Last Updated**: 2025-11-25

## Overview

The `aegis agent` command provides a complete workflow-managed task execution system using Claude Code CLI. It handles the entire lifecycle of task processing from Asana assignment through completion, including:

- Automatic task workflow management (section movement)
- Agent tracking and identification
- Headless or terminal-based execution
- Result posting and task completion
- Comprehensive logging and database tracking

## Command Signature

```bash
aegis agent [OPTIONS]
```

### Required Options

| Option | Description | Example |
|--------|-------------|---------|
| `--task-id TEXT` | Asana task ID (GID) to process | `--task-id 1234567890` |

### Optional Options

| Option | Default | Description |
|--------|---------|-------------|
| `--agent-name TEXT` | `aegis-agent` | Name of the agent for tracking |
| `--prompt TEXT` | None | Additional instructions for the agent |
| `--log TEXT` | `logs/agent.log` | Path to log file |
| `--timeout INTEGER` | `1800` | Execution timeout in seconds (30 min) |
| `--terminal / --no-terminal` | `--no-terminal` | Launch in new terminal window |

## Usage Examples

### Basic Usage (Headless)

```bash
# Execute a task with default settings
aegis agent --task-id 1234567890
```

### With Custom Agent Name

```bash
# Track execution under a specific agent name
aegis agent --task-id 1234567890 --agent-name production-bot
```

### With Additional Prompt

```bash
# Provide extra instructions
aegis agent --task-id 1234567890 \
  --prompt "Be extra careful with tests. Run all test suites before completing."
```

### With Custom Timeout

```bash
# Set 1 hour timeout for complex tasks
aegis agent --task-id 1234567890 --timeout 3600
```

### Terminal Mode

```bash
# Launch in new terminal window to watch execution
aegis agent --task-id 1234567890 --terminal
```

### Complete Example

```bash
# Full-featured execution
aegis agent \
  --task-id 1234567890 \
  --agent-name code-review-bot \
  --prompt "Focus on security and performance issues" \
  --log logs/code-review.log \
  --timeout 2400 \
  --no-terminal
```

## Execution Workflow

The command follows an 8-step process:

### 1. Fetch Task from Asana

```
✓ Fetches task details including name, description, project
✓ Retrieves project information and code location
✓ Validates task is in a project
```

### 2. Manage Task Workflow

```
✓ Moves task to "In Progress" section (if exists)
✓ Posts comment marking agent start
✓ Tracks agent name in comments
```

**Note**: Custom field support for `agent=<name>` is noted in comments. Direct custom field updates require project-specific field GIDs.

### 3. Create Execution Record

```
✓ Creates TaskExecution record in database
✓ Tracks: task GID, project, agent name, start time
✓ Stores context including code path and additional prompt
```

### 4. Prepare Claude Code Execution

```
✓ Builds comprehensive prompt from:
  - Task name and description
  - Project context
  - Code location
  - Additional instructions (if provided)
✓ Determines working directory
✓ Adds exit instruction
```

### 5. Execute with Claude Code CLI

**Headless Mode** (default):
```
✓ Runs Claude Code as subprocess
✓ Captures stdout and stderr
✓ Enforces timeout
✓ Tracks with shutdown handler
```

**Terminal Mode** (`--terminal`):
```
✓ Launches in new Hyper terminal window
✓ Auto-exits on completion
✓ Returns exit code (no output capture)
```

### 6. Process Results

```
✓ Calculates execution duration
✓ Determines success/failure
✓ Updates database execution record
```

### 7. Post Results to Asana

```
✓ Posts comprehensive result comment:
  - Status emoji (✅/❌)
  - Agent name
  - Duration
  - Execution ID
  - Output (first 5000 chars)
```

### 8. Update Task Status

**On Success**:
```
✓ Marks task as complete
✓ Moves to "Implemented" section (if exists)
```

**On Failure**:
```
✓ Leaves task incomplete
✓ Keeps in current section for review
```

## Output Format

### Console Output

```
Aegis Agent: my-agent
Task ID: 1234567890
Timeout: 1800s

1. Fetching task from Asana...
   ✓ Task: Build SimpleExecutor agent
   ✓ Project: Aegis
   ✓ Code location: /Users/me/code/aegis

2. Managing task workflow...
   → Moving task to 'In Progress' section...
   ✓ Moved to 'In Progress'
   → Setting agent: my-agent
   ✓ Agent tracked in comments

3. Creating execution record...
   ✓ Execution ID: 42

4. Preparing Claude Code execution...
   ✓ Working directory: /Users/me/code/aegis

5. Executing with Claude Code CLI...
   Timeout: 1800s
   Mode: Headless

   Running headless (output will be captured)...

6. Processing results...
   Duration: 145s
   Success: True

7. Posting results to Asana...
   ✓ Posted result comment
   ✓ Logged to: logs/agent.log

8. Marking task complete...
   ✓ Task marked as complete
   ✓ Moved to 'Implemented' section

✓ Agent execution complete!
Task URL: https://app.asana.com/0/1234567890/9876543210
Execution ID: 42
Log: logs/agent.log
```

### Log File Format

```
================================================================================
Execution: 42
Task: Build SimpleExecutor agent (1234567890)
Agent: my-agent
Started: 2025-11-25T10:30:00
Duration: 145s
Success: True
================================================================================
[Output from Claude Code CLI execution...]
================================================================================
```

### Asana Comments

**Start Comment**:
```markdown
🤖 **Agent Started**: my-agent

Execution started at 2025-11-25T10:30:00
```

**Result Comment**:
```markdown
✅ **Task completed successfully**

**Agent**: my-agent
**Duration**: 145s
**Execution ID**: 42

**Output**:
```
I've successfully completed the task...
[output continues...]
```

🤖 Executed via `aegis agent` command
```

## Database Tracking

Each execution creates a `TaskExecution` record:

```python
TaskExecution(
    id=42,
    task_id=None,                      # Not linked to Task table yet
    status="completed",                # or "failed"
    agent_type="my-agent",             # From --agent-name
    started_at=datetime(...),
    completed_at=datetime(...),
    duration_seconds=145,
    success=True,
    output="[Claude output]",
    error_message=None,
    context={
        "asana_task_gid": "1234567890",
        "asana_task_name": "Build SimpleExecutor agent",
        "project_gid": "9876543210",
        "project_name": "Aegis",
        "code_path": "/Users/me/code/aegis",
        "additional_prompt": "Be careful with tests",
    }
)
```

Query executions:

```python
from aegis.database.session import get_db_session
from aegis.database.models import TaskExecution

with get_db_session() as session:
    # Get all executions for an agent
    executions = session.query(TaskExecution)\
        .filter(TaskExecution.agent_type == "my-agent")\
        .order_by(TaskExecution.started_at.desc())\
        .all()

    # Get successful executions
    successful = session.query(TaskExecution)\
        .filter(TaskExecution.success == True)\
        .count()
```

## Error Handling

### Timeout Handling

```bash
# Task exceeds timeout
❌ Execution timeout (1800s)

# Process is killed
# Partial output captured
# Marked as failed in database
# Posted to Asana with timeout indication
```

### Execution Failures

```bash
# Non-zero exit code
✗ Task failed

# Error details captured
# Posted to Asana with error output
# Task left incomplete for review
```

### Asana Errors

```bash
# Task not found
✗ Error: Task not found in Asana

# Not in project
✗ Error: Task is not in any project

# Section not found
⚠ 'In Progress' section not found, skipping move
```

## Configuration

### Environment Variables

The command uses configuration from `.env`:

```bash
# Required
ASANA_ACCESS_TOKEN=your_token_here

# Optional
AEGIS_DEFAULT_TIMEOUT=1800
AEGIS_DEFAULT_LOG_PATH=logs/agent.log
```

### Project Setup

For the command to work optimally, projects should have:

1. **Code Location** in project notes:
   ```
   Code Location: /Users/me/code/myproject
   ```

2. **Standard Sections**:
   - "In Progress" (target for active tasks)
   - "Implemented" (target for completed tasks)

Create sections:
```bash
aegis organize <project-name>
```

## Integration with Other Commands

### With `aegis work-on`

The `aegis work-on` command can use `aegis agent` internally:

```bash
# Process multiple tasks
aegis work-on Aegis --max-tasks 5
```

### With Orchestrator

Configure orchestrator to use agent mode:

```python
# In .env
EXECUTION_MODE=claude_cli

# Orchestrator will execute tasks similar to agent command
aegis orchestrate
```

## Performance Characteristics

### Execution Time

| Component | Typical Time |
|-----------|-------------|
| Task fetch | 0.5-2s |
| Workflow management | 1-3s |
| Database ops | <0.1s |
| Claude execution | 10-300s (task dependent) |
| Result posting | 1-2s |
| **Total** | **15s - 5min** (typical) |

### Resource Usage

- **Memory**: ~50MB base + Claude Code CLI overhead
- **CPU**: Depends on task (compilation, testing, etc.)
- **Network**: Minimal (Asana API calls only)
- **Disk**: Log file grows with each execution

### Cost

- **Claude API**: $0.01-$1.00 per task (depends on complexity)
- **Asana API**: Free (within rate limits)
- **No additional infrastructure costs**

## Troubleshooting

### Issue: Task ID not found

```bash
✗ Error: Task not found in Asana
```

**Solution**: Verify task ID is correct:
```bash
# Check task URL: https://app.asana.com/0/PROJECT/TASK
# Use TASK portion as --task-id
```

### Issue: Permission denied for code location

```bash
✗ Error: Permission denied: /path/to/code
```

**Solution**: Check code path permissions:
```bash
ls -la /path/to/code
# Ensure you have read/write access
```

### Issue: Timeout too short

```bash
❌ Execution timeout (1800s)
```

**Solution**: Increase timeout:
```bash
aegis agent --task-id 123 --timeout 3600  # 1 hour
```

### Issue: Claude CLI not found

```bash
✗ Error: claude: command not found
```

**Solution**: Install Claude Code CLI:
```bash
# Follow installation instructions at:
# https://claude.com/claude-code
```

### Issue: Terminal mode not working

```bash
✗ Error: osascript is not allowed to send keystrokes
```

**Solution**: Grant accessibility permissions:
- System Settings → Privacy & Security → Accessibility
- Add Terminal app

## Best Practices

### 1. Use Descriptive Agent Names

```bash
# Good
--agent-name code-review-bot
--agent-name test-runner
--agent-name deployment-agent

# Less useful
--agent-name agent1
--agent-name bot
```

### 2. Provide Clear Additional Prompts

```bash
# Good
--prompt "Focus on security issues. Check for SQL injection and XSS vulnerabilities."

# Too vague
--prompt "Be careful"
```

### 3. Set Appropriate Timeouts

```bash
# Quick tasks (analysis, review)
--timeout 600  # 10 minutes

# Medium tasks (implementation)
--timeout 1800  # 30 minutes (default)

# Complex tasks (refactoring, migration)
--timeout 3600  # 1 hour
```

### 4. Use Custom Log Files for Different Agents

```bash
# Separate logs per agent type
aegis agent --task-id 123 --agent-name code-review --log logs/code-review.log
aegis agent --task-id 456 --agent-name testing --log logs/testing.log
```

### 5. Use Terminal Mode for Debugging

```bash
# Watch execution in real-time
aegis agent --task-id 123 --terminal
```

### 6. Monitor Execution History

```python
# Query database for agent performance
from aegis.database.session import get_db_session
from aegis.database.models import TaskExecution
from sqlalchemy import func

with get_db_session() as session:
    stats = session.query(
        TaskExecution.agent_type,
        func.count(TaskExecution.id).label('total'),
        func.avg(TaskExecution.duration_seconds).label('avg_duration'),
        func.sum(case((TaskExecution.success == True, 1), else_=0)).label('successful')
    ).group_by(TaskExecution.agent_type).all()

    for stat in stats:
        print(f"{stat.agent_type}: {stat.successful}/{stat.total} success, avg {stat.avg_duration}s")
```

## Comparison with Other Execution Methods

| Feature | `aegis agent` | `aegis do` | `aegis work-on` | SimpleExecutor |
|---------|--------------|------------|----------------|----------------|
| **Workflow Management** | ✅ Full | ❌ No | ✅ Full | ❌ No |
| **Section Movement** | ✅ Yes | ❌ No | ✅ Yes | ❌ No |
| **Agent Tracking** | ✅ Yes | ❌ No | ✅ Yes | ✅ Yes |
| **Code Execution** | ✅ Claude CLI | ✅ Claude CLI | ✅ Claude CLI | ❌ API only |
| **Database Logging** | ✅ Yes | ✅ Yes | ✅ Yes | ✅ Yes |
| **Multiple Tasks** | ❌ No | ❌ No | ✅ Yes | ❌ No |
| **Terminal Mode** | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |
| **Custom Prompts** | ✅ Yes | ❌ No | ❌ No | ✅ Yes |
| **Timeout Control** | ✅ Yes | ❌ Fixed | ❌ Fixed | ✅ Yes |

**Use `aegis agent` when**:
- Need full workflow management
- Want agent tracking
- Need custom prompts or timeouts
- Processing single task with care

**Use `aegis do` when**:
- Quick one-off execution
- Don't need workflow management
- First task in project

**Use `aegis work-on` when**:
- Processing multiple tasks
- Autonomous operation
- Want automatic task selection

**Use SimpleExecutor when**:
- Only need analysis/planning
- Want lower cost
- No code changes needed

## Examples

### Example 1: Code Review

```bash
aegis agent \
  --task-id 1234567890 \
  --agent-name code-review-bot \
  --prompt "Review code for:
  - Security vulnerabilities
  - Performance issues
  - Code style consistency
  - Test coverage" \
  --timeout 900 \
  --log logs/code-review.log
```

### Example 2: Bug Fix

```bash
aegis agent \
  --task-id 9876543210 \
  --agent-name bug-fixer \
  --prompt "Fix the bug. Add regression test. Update documentation if needed." \
  --timeout 2400
```

### Example 3: Documentation

```bash
aegis agent \
  --task-id 5555555555 \
  --agent-name docs-writer \
  --prompt "Write comprehensive documentation with examples. Use clear, concise language." \
  --timeout 1200
```

### Example 4: Testing

```bash
aegis agent \
  --task-id 7777777777 \
  --agent-name test-runner \
  --prompt "Run all test suites. If failures, investigate and fix. Add new tests if coverage gaps found." \
  --timeout 3600
```

## See Also

- [CLI Reference](../TOOLS.md) - All CLI commands
- [SimpleExecutor Documentation](../src/aegis/agents/SIMPLE_EXECUTOR.md) - API-based agent
- [Orchestrator Guide](./OPERATOR_GUIDE.md) - Autonomous operation
- [Shutdown Handling](./SHUTDOWN_HANDLING.md) - Graceful termination

---

**Command**: `aegis agent`
**Status**: ✅ Production Ready
**Version**: 1.0.0
**Last Updated**: 2025-11-25
