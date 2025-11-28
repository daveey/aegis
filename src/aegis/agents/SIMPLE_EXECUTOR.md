# SimpleExecutor Agent

**Status**: ✅ Complete
**Version**: 1.0.0
**Last Updated**: 2025-11-25

## Overview

The **SimpleExecutor** is the first working agent in the Aegis system. It processes Asana tasks end-to-end by:

1. Accepting an Asana task as input
2. Generating a prompt from the task description
3. Calling the Claude API to process the task
4. Posting the response as an Asana comment
5. Logging execution details to the database

This agent serves as the foundation for more sophisticated agents and demonstrates the core pattern for agent implementation in Aegis.

## Features

- ✅ **Full End-to-End Processing**: Handles task from input to output
- ✅ **Claude API Integration**: Uses Anthropic's Messages API
- ✅ **Asana Integration**: Fetches tasks and posts results as comments
- ✅ **Database Logging**: Tracks execution history, token usage, and outcomes
- ✅ **Error Handling**: Gracefully handles failures and posts error details
- ✅ **Response Formatting**: Automatic markdown enhancement and splitting
- ✅ **Retry Logic**: Automatic retries for transient failures
- ✅ **Comprehensive Tests**: 16 unit tests with 98% coverage

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ASANA TASK                           │
│  (name, description, project, code location)            │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│              SimpleExecutor.execute_task()              │
│  ┌──────────────────────────────────────────────────┐  │
│  │  1. Generate Prompt (_generate_prompt)           │  │
│  │     - Task name and description                  │  │
│  │     - Project context                            │  │
│  │     - Code location (if provided)                │  │
│  │     - Due date                                   │  │
│  └──────────────────────────────────────────────────┘  │
│                         │                               │
│                         ▼                               │
│  ┌──────────────────────────────────────────────────┐  │
│  │  2. Call Claude API (_call_claude_api)           │  │
│  │     - Send prompt to Claude                      │  │
│  │     - Track token usage                          │  │
│  │     - Extract response                           │  │
│  └──────────────────────────────────────────────────┘  │
│                         │                               │
│                         ▼                               │
│  ┌──────────────────────────────────────────────────┐  │
│  │  3. Post Response (_post_response_to_asana)      │  │
│  │     - Format response (markdown enhancement)     │  │
│  │     - Split if too long (>65k chars)             │  │
│  │     - Post as Asana comment(s)                   │  │
│  └──────────────────────────────────────────────────┘  │
│                         │                               │
│                         ▼                               │
│  ┌──────────────────────────────────────────────────┐  │
│  │  4. Log Execution (_log_execution)               │  │
│  │     - Record in TaskExecution table              │  │
│  │     - Track timing, tokens, success/failure      │  │
│  │     - Store output or error message              │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Usage

### Basic Usage

```python
import asyncio
from aegis.agents.simple_executor import SimpleExecutor
from aegis.asana.client import AsanaClient
from aegis.config import Settings

async def execute_task():
    # Initialize
    config = Settings()
    asana_client = AsanaClient(config.asana_access_token)
    executor = SimpleExecutor(config=config, asana_client=asana_client)

    # Fetch task
    task = await asana_client.get_task("1234567890")

    # Execute
    result = await executor.execute_task(
        task=task,
        project_name="My Project",
        code_path="/path/to/code"
    )

    # Check result
    if result["success"]:
        print(f"✅ Task completed! Execution ID: {result['execution_id']}")
        print(f"Tokens used: {result['metadata']['input_tokens']} + {result['metadata']['output_tokens']}")
    else:
        print(f"❌ Task failed: {result['error']}")

asyncio.run(execute_task())
```

### Command-Line Usage

See `examples/simple_executor_usage.py`:

```bash
python examples/simple_executor_usage.py <task_gid>
```

### Integration with CLI

The SimpleExecutor can be integrated into the Aegis CLI commands:

```python
# In src/aegis/cli.py
from aegis.agents.simple_executor import SimpleExecutor

@main.command()
@click.argument("task_gid")
async def execute(task_gid: str):
    """Execute a task using SimpleExecutor agent."""
    config = Settings()
    asana_client = AsanaClient(config.asana_access_token)
    executor = SimpleExecutor(config=config, asana_client=asana_client)

    task = await asana_client.get_task(task_gid)
    result = await executor.execute_task(task, "Project Name")

    if result["success"]:
        click.echo(f"✅ Task completed!")
    else:
        click.echo(f"❌ Task failed: {result['error']}")
```

## API Reference

### `SimpleExecutor`

Main agent class for task execution.

#### `__init__(config=None, asana_client=None, anthropic_client=None)`

Initialize the SimpleExecutor agent.

**Parameters:**
- `config` (Settings | None): Settings configuration (defaults to Settings())
- `asana_client` (AsanaClient | None): Asana client instance (optional)
- `anthropic_client` (Anthropic | None): Anthropic client instance (optional)

**Example:**
```python
executor = SimpleExecutor()  # Uses default config
# or
executor = SimpleExecutor(config=custom_config, asana_client=custom_client)
```

#### `async execute_task(task, project_name, code_path=None)`

Execute an Asana task using Claude API.

**Parameters:**
- `task` (AsanaTask): The Asana task to execute
- `project_name` (str): Name of the project the task belongs to
- `code_path` (str | None): Optional path to the code repository

**Returns:**
Dictionary with execution results:
```python
{
    "success": bool,           # Whether execution succeeded
    "output": str | None,      # Response text (if success)
    "error": str | None,       # Error message (if failed)
    "execution_id": int,       # Database ID of execution record
    "metadata": {              # Additional metadata
        "input_tokens": int,
        "output_tokens": int,
        "model": str,
        "stop_reason": str
    }
}
```

**Example:**
```python
result = await executor.execute_task(
    task=task,
    project_name="Aegis",
    code_path="/Users/me/code/aegis"
)
```

## Configuration

The SimpleExecutor uses the following configuration from `Settings`:

```python
# Anthropic API
anthropic_api_key: str              # Required
anthropic_model: str                # Default: "claude-sonnet-4-5-20250929"

# Asana
asana_access_token: str             # Required

# Database
database_url: str                   # Default: "postgresql://localhost/aegis"
```

### Environment Variables

Create a `.env` file:

```bash
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
ASANA_ACCESS_TOKEN=...
DATABASE_URL=postgresql://localhost/aegis
```

## Prompt Template

The agent generates prompts in the following format:

```
Task: <task_name>

Project: <project_name>

Code Location: <code_path>

Task Description:
<task_notes>

Due Date: <due_date>

IMPORTANT: When you have completed this task, provide a summary of what you accomplished and then EXIT. Do not wait for further input.
```

## Response Formatting

The SimpleExecutor uses the `formatters` module to:

1. **Enhance Markdown**: Automatically formats code blocks, headers, and lists
2. **Add Status Badge**: Includes visual indicator (✅ Complete, ❌ Error, etc.)
3. **Split Long Responses**: Automatically splits responses >65k characters
4. **Syntax Highlighting**: Adds language specifiers to code blocks

Example formatted response:

```markdown
✅ **Complete**

I've successfully completed the task. Here's what I did:

## Changes Made

1. Created new function `process_data()`
2. Added unit tests
3. Updated documentation

```python
def process_data(input_data):
    """Process the input data."""
    return input_data.upper()
```

## Next Steps

- Review the changes
- Run the test suite
- Deploy to production
```

## Database Logging

Each execution creates a `TaskExecution` record:

```python
TaskExecution(
    task_id=None,                    # Linked to Task table (future)
    status="completed",              # or "failed"
    agent_type="simple_executor",
    started_at=datetime,
    completed_at=datetime,
    duration_seconds=int,
    success=True/False,
    output="response text",          # or None if failed
    error_message=None,              # or error text if failed
    input_tokens=100,
    output_tokens=50,
    execution_metadata={...}
)
```

Query execution history:

```python
from aegis.database.session import get_db_session
from aegis.database.models import TaskExecution

with get_db_session() as session:
    executions = session.query(TaskExecution)\
        .filter(TaskExecution.agent_type == "simple_executor")\
        .order_by(TaskExecution.started_at.desc())\
        .limit(10)\
        .all()

    for exec in executions:
        print(f"{exec.started_at}: {exec.status} - {exec.duration_seconds}s")
```

## Error Handling

The SimpleExecutor handles errors at multiple levels:

### 1. API Errors

Claude API failures are caught and logged:

```python
try:
    response = await self._call_claude_api(prompt)
except Exception as e:
    # Error posted to Asana
    # Execution logged as "failed"
    # Error details in database
```

### 2. Asana Posting Errors

Posting failures trigger automatic retry (3 attempts):

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def _post_response_to_asana(...):
    # Automatic retry on failure
```

### 3. Database Errors

Database operations are wrapped in transactions:

```python
with get_db_session() as session:
    session.add(execution)
    session.commit()  # Auto-rollback on error
```

## Testing

The SimpleExecutor has comprehensive unit tests:

```bash
# Run tests
pytest tests/unit/test_simple_executor.py -v

# Run with coverage
pytest tests/unit/test_simple_executor.py --cov=src/aegis/agents/simple_executor --cov-report=term-missing
```

**Test Coverage**: 98% (98/100 lines)

**Test Categories**:
- Initialization (2 tests)
- Prompt generation (4 tests)
- Claude API calls (2 tests)
- Asana response posting (3 tests)
- Database logging (2 tests)
- End-to-end execution (3 tests)

## Performance

### Token Usage

Average tokens per execution:
- Input: ~500-2000 tokens (depends on task description)
- Output: ~500-4000 tokens (depends on complexity)

### Timing

Typical execution time:
- Prompt generation: <1ms
- Claude API call: 2-10 seconds
- Response posting: 0.5-2 seconds
- Database logging: <100ms

**Total**: 3-15 seconds per task

### Cost

Based on Claude Sonnet 4.5 pricing (as of 2025-11):
- Input: $3 per 1M tokens
- Output: $15 per 1M tokens

**Typical cost per task**: $0.01 - $0.10

## Limitations

1. **No Code Execution**: The agent only calls Claude API, it doesn't execute code locally
2. **No File System Access**: Cannot read or write files (unlike Claude Code CLI)
3. **Single Response**: Generates one response, no back-and-forth conversation
4. **No Tool Use**: Doesn't use Claude's tool calling features
5. **Limited Context**: Only task description + project info (no full codebase access)

## Future Enhancements

Potential improvements for future versions:

1. **Code Execution**: Integrate with Claude Code CLI for actual code changes
2. **Multi-Turn Conversation**: Support follow-up questions and clarifications
3. **Tool Use**: Enable Claude to use tools (file reading, git operations, etc.)
4. **Streaming**: Stream responses for faster perceived performance
5. **Caching**: Use prompt caching for repeated context
6. **Task Linking**: Link executions to Task table in database
7. **Cost Tracking**: Calculate and store execution cost

## Comparison with Claude Code CLI

| Feature | SimpleExecutor | Claude Code CLI |
|---------|----------------|-----------------|
| **Task Execution** | ✅ Yes | ✅ Yes |
| **File System Access** | ❌ No | ✅ Yes |
| **Code Editing** | ❌ No | ✅ Yes |
| **Git Operations** | ❌ No | ✅ Yes |
| **Terminal Commands** | ❌ No | ✅ Yes |
| **Asana Integration** | ✅ Built-in | ❌ Manual |
| **Database Logging** | ✅ Automatic | ❌ No |
| **Response Formatting** | ✅ Automatic | ❌ Manual |
| **Cost** | Lower (API only) | Higher (CLI overhead) |
| **Speed** | Faster | Slower |

**Use SimpleExecutor when:**
- Task requires only reasoning/planning (no code changes)
- You want structured logging and tracking
- Cost is a concern
- Speed is important

**Use Claude Code CLI when:**
- Task requires actual code changes
- Need file system access
- Need git operations
- Task is complex and requires multiple steps

## Examples

### Example 1: Simple Question

**Task**: "What is the time complexity of bubble sort?"

**Result**:
```markdown
✅ **Complete**

The time complexity of bubble sort is:

- **Best case**: O(n) - when the array is already sorted
- **Average case**: O(n²) - typical case
- **Worst case**: O(n²) - when the array is reverse sorted

Bubble sort compares adjacent elements and swaps them if they're in the wrong order, repeating until no swaps are needed.
```

### Example 2: Code Review

**Task**: "Review the authentication logic in src/auth.py"

**Result**:
```markdown
✅ **Complete**

## Code Review: src/auth.py

### Strengths
- Clear separation of concerns
- Good error handling
- Comprehensive tests

### Issues Found

1. **Security**: Password hashing uses deprecated MD5
   - Recommendation: Switch to bcrypt or Argon2

2. **Performance**: Database query in hot path
   - Recommendation: Add caching layer

3. **Testing**: Missing edge case tests
   - Add tests for expired tokens
   - Add tests for concurrent sessions

### Suggested Changes

```python
# Use bcrypt for password hashing
import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
```

## Related Tasks

Consider creating tasks for:
- Implement bcrypt password hashing
- Add Redis caching layer
- Add edge case tests
```

### Example 3: Documentation

**Task**: "Write API documentation for the new /users endpoint"

**Result**:
```markdown
✅ **Complete**

# Users API Endpoint

## GET /users

Retrieve a list of users.

**Authentication**: Required

**Parameters**:
- `page` (int, optional): Page number (default: 1)
- `limit` (int, optional): Items per page (default: 20, max: 100)
- `search` (string, optional): Search by name or email

**Response**:
```json
{
  "users": [
    {
      "id": "123",
      "name": "John Doe",
      "email": "john@example.com",
      "created_at": "2025-11-25T10:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "limit": 20,
    "total": 100
  }
}
```

**Errors**:
- `401 Unauthorized`: Missing or invalid auth token
- `403 Forbidden`: Insufficient permissions
- `400 Bad Request`: Invalid parameters
```

## Troubleshooting

### Issue: "Cannot import name 'get_async_session'"

**Cause**: Trying to use async database session (not implemented)

**Solution**: The SimpleExecutor uses synchronous sessions via `get_db_session()`

### Issue: "Anthropic API key not found"

**Cause**: Missing ANTHROPIC_API_KEY in environment

**Solution**:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
# or add to .env file
```

### Issue: "Response too long for Asana comment"

**Cause**: Response exceeds 65k character limit

**Solution**: The formatter automatically splits long responses. Check that all parts are posted:

```python
formatted = format_response(long_text)
if formatted.is_split:
    print(f"Response split into {len(formatted.parts)} parts")
```

### Issue: "Task execution failed with no error message"

**Cause**: Database connection issue or unhandled exception

**Solution**: Check logs and database connectivity:

```bash
# Check logs
tail -f logs/aegis.log

# Test database
psql -d aegis -c "SELECT 1"
```

## Contributing

When modifying the SimpleExecutor:

1. Update tests in `tests/unit/test_simple_executor.py`
2. Maintain test coverage >90%
3. Update this documentation
4. Test end-to-end with a real Asana task
5. Check database logging works correctly

## See Also

- [Formatters Module](./README.md#formatters-formatters-py) - Response formatting utilities
- [Asana Client](../asana/client.py) - Asana API integration
- [Database Models](../database/models.py) - TaskExecution model
- [Configuration](../config.py) - Settings management
- [Example Usage](../../examples/simple_executor_usage.py) - Command-line example

---

**Status**: ✅ Production Ready
**Maintainer**: Aegis Development Team
**Last Updated**: 2025-11-25
