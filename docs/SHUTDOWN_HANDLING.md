# Graceful Shutdown Handling

Aegis implements comprehensive graceful shutdown handling to ensure no work is lost when the system is terminated.

## Overview

The shutdown system provides:

1. **Signal Handling** - Catches SIGTERM and SIGINT (Ctrl+C)
2. **Task Completion** - Waits for in-progress tasks to finish
3. **Subprocess Management** - Gracefully terminates child processes
4. **Database Cleanup** - Closes all active database sessions
5. **State Persistence** - Saves system state before exit
6. **Timeout Protection** - Forces shutdown after maximum wait time

## Architecture

### Components

- **`src/aegis/utils/shutdown.py`** - Core shutdown handler implementation
- **`src/aegis/database/state.py`** - System state management and persistence
- **`src/aegis/database/session.py`** - Database connection cleanup
- **`src/aegis/config.py`** - Shutdown timeout configuration

### Key Classes

#### `ShutdownHandler`

The main class managing graceful shutdown. Features:

- Singleton pattern via `get_shutdown_handler()`
- Signal handler installation/restoration
- Task, subprocess, and session tracking
- Configurable timeouts
- Cleanup callback registry

## Usage

### Basic Setup

```python
from aegis.utils.shutdown import get_shutdown_handler
from aegis.database.state import mark_orchestrator_stopped_async
from aegis.database.session import cleanup_db_connections

# Initialize handler with custom timeouts (optional)
shutdown_handler = get_shutdown_handler(
    shutdown_timeout=300,         # 5 minutes max wait for tasks
    subprocess_term_timeout=10    # 10 seconds for subprocess SIGTERM
)

# Install signal handlers for SIGINT and SIGTERM
shutdown_handler.install_signal_handlers()

# Register cleanup callbacks (called during shutdown)
shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
shutdown_handler.register_cleanup_callback(cleanup_db_connections)
```

### Tracking Resources

#### Asyncio Tasks

```python
async def my_task():
    # Your task logic
    pass

task = asyncio.create_task(my_task())
shutdown_handler.track_task(task)  # Automatically untracked when complete
```

#### Subprocesses

```python
import subprocess

process = subprocess.Popen(["command", "arg"])
shutdown_handler.track_subprocess(process)

# Later, when done:
shutdown_handler.untrack_subprocess(process)
```

#### Database Sessions

```python
from aegis.database.session import get_db

session = get_db()
shutdown_handler.track_session(session)

# Later, when done:
shutdown_handler.untrack_session(session)
```

### Checking for Shutdown

Check if shutdown has been requested in long-running loops:

```python
while not shutdown_handler.shutdown_requested:
    # Do work
    await process_next_item()

    # Check again before continuing
    if shutdown_handler.shutdown_requested:
        logger.info("Shutdown requested, stopping work")
        break
```

### Executing Shutdown

```python
try:
    # Your main application logic
    await run_application()
finally:
    # Always execute shutdown sequence
    await shutdown_handler.shutdown()
```

## Shutdown Sequence

When shutdown is triggered (via signal or manual call), the following sequence executes:

1. **Request Shutdown** - Sets shutdown flag and logs current state
2. **Wait for Tasks** - Allows asyncio tasks to complete (up to `shutdown_timeout`)
3. **Terminate Subprocesses** - Sends SIGTERM, waits (`subprocess_term_timeout`), then SIGKILL if needed
4. **Close Sessions** - Closes all tracked database sessions
5. **Run Callbacks** - Executes registered cleanup functions in order:
   - Mark interrupted tasks in database
   - Mark orchestrator as stopped
   - Clean up database connections (dispose engine)
6. **Restore Handlers** - Restores original signal handlers

## Configuration

Configure shutdown timeouts in `.env` or environment variables:

```bash
# Maximum seconds to wait for tasks during shutdown (default: 300)
SHUTDOWN_TIMEOUT=300

# Seconds to wait after SIGTERM before SIGKILL for subprocesses (default: 10)
SUBPROCESS_TERM_TIMEOUT=10
```

Access configuration:

```python
from aegis.config import get_settings

settings = get_settings()
print(f"Shutdown timeout: {settings.shutdown_timeout}s")
print(f"Subprocess timeout: {settings.subprocess_term_timeout}s")
```

## Integration Examples

### CLI Commands

The `do` and `work-on` commands in `src/aegis/cli.py` demonstrate full integration:

```python
@main.command()
def do(project_name: str) -> None:
    """Execute a task with graceful shutdown."""

    async def _do() -> None:
        # Initialize shutdown handler
        shutdown_handler = get_shutdown_handler(shutdown_timeout=300)
        shutdown_handler.install_signal_handlers()

        # Register cleanup callbacks
        shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
        shutdown_handler.register_cleanup_callback(cleanup_db_connections)

        try:
            # Run subprocess with tracking
            process = subprocess.Popen(["claude", task_context])
            shutdown_handler.track_subprocess(process)

            try:
                stdout, stderr = process.communicate(timeout=300)
            finally:
                shutdown_handler.untrack_subprocess(process)

        finally:
            # Always run shutdown
            await shutdown_handler.shutdown()

    try:
        asyncio.run(_do())
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        sys.exit(130)
```

### Long-Running Orchestrator

For a long-running orchestrator loop:

```python
async def orchestrator_loop():
    """Main orchestrator loop with shutdown handling."""
    shutdown_handler = get_shutdown_handler()
    shutdown_handler.install_signal_handlers()

    # Register cleanup
    shutdown_handler.register_cleanup_callback(mark_in_progress_tasks_interrupted_async)
    shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
    shutdown_handler.register_cleanup_callback(cleanup_db_connections)

    try:
        mark_orchestrator_running()

        while not shutdown_handler.shutdown_requested:
            # Poll for new tasks
            tasks = await fetch_new_tasks()

            # Execute tasks
            for task in tasks:
                # Check before starting new work
                if shutdown_handler.shutdown_requested:
                    logger.info("Shutdown requested, not starting new tasks")
                    break

                task_coro = execute_task(task)
                task_obj = asyncio.create_task(task_coro)
                shutdown_handler.track_task(task_obj)

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    finally:
        await shutdown_handler.shutdown()
```

## Testing

### Unit Tests

Run the comprehensive unit test suite:

```bash
pytest tests/unit/test_shutdown.py -v
```

Test coverage includes:
- Signal handler installation/restoration
- Task tracking and completion waiting
- Subprocess termination (graceful and forced)
- Database session cleanup
- Cleanup callback execution (sync and async)
- Timeout behavior
- Error handling

### Manual Testing

Use the interactive test script to verify shutdown behavior:

```bash
# Quick tasks (completes before timeout)
python tests/manual_shutdown_test.py quick

# Slow tasks (tests timeout behavior)
python tests/manual_shutdown_test.py slow

# Subprocess handling
python tests/manual_shutdown_test.py subprocess

# Database session cleanup
python tests/manual_shutdown_test.py database

# Run all scenarios
python tests/manual_shutdown_test.py all
```

During each test, press **Ctrl+C** to trigger graceful shutdown and observe:
- Signal caught and logged
- Tasks completing or timing out
- Subprocesses terminated gracefully
- Database connections closed
- State saved

### Integration Testing

Test with real CLI commands:

```bash
# Start a command and press Ctrl+C during execution
aegis do "project-name"

# Should see:
# - "Shutdown requested" message
# - Tasks completing or stopping gracefully
# - "Shutdown complete" message
# - Exit code 130 (standard for SIGINT)
```

## Monitoring and Logging

Shutdown events are logged with structured logging:

```python
# When shutdown is requested
logger.info(
    "shutdown_requested",
    signal="SIGINT",
    in_progress_tasks=3,
    in_progress_subprocesses=1,
    active_sessions=2
)

# Task completion
logger.info("all_tasks_completed")

# Or timeout
logger.warning(
    "shutdown_timeout_exceeded",
    remaining_tasks=2,
    timeout=300
)

# Subprocess termination
logger.info("subprocess_terminated_gracefully", pid=12345)

# Or forced kill
logger.warning("sending_sigkill_to_subprocess", pid=12345)

# Session cleanup
logger.info("closing_database_sessions", count=2)

# Final status
logger.info(
    "shutdown_sequence_completed",
    clean_shutdown=True,
    tasks_completed=True,
    subprocesses_terminated=True
)
```

## Acceptance Criteria Status

✅ **Ctrl+C shuts down cleanly**
- SIGINT and SIGTERM signals are caught
- Shutdown sequence executes automatically
- Original signal handlers restored

✅ **In-progress tasks complete**
- Tasks are tracked and waited for
- Configurable timeout (default: 5 minutes)
- Tasks can check `shutdown_requested` flag

✅ **State saved correctly**
- System state marked as stopped
- In-progress tasks marked as interrupted
- Cleanup callbacks execute reliably

✅ **No database connections left open**
- Active sessions tracked and closed
- Database engine disposed
- Connection pool cleaned up

## Best Practices

1. **Always use the shutdown handler** - Don't implement custom signal handlers
2. **Track all long-running resources** - Tasks, subprocesses, sessions
3. **Check shutdown flag in loops** - Stop accepting new work when shutdown requested
4. **Use try/finally** - Ensure shutdown sequence always runs
5. **Register cleanup callbacks** - For component-specific cleanup
6. **Choose appropriate timeouts** - Balance graceful completion vs. quick shutdown
7. **Handle KeyboardInterrupt** - Exit with code 130 for SIGINT

## Troubleshooting

### Tasks not completing during shutdown

**Symptom**: Shutdown timeout exceeded, tasks cancelled

**Solutions**:
- Increase `shutdown_timeout` in configuration
- Check for tasks stuck in blocking I/O
- Ensure tasks check `shutdown_requested` flag
- Verify tasks are properly tracked

### Subprocesses not terminating

**Symptom**: Subprocesses force-killed with SIGKILL

**Solutions**:
- Increase `subprocess_term_timeout`
- Ensure subprocess handles SIGTERM gracefully
- Check subprocess isn't ignoring signals
- Verify process is being tracked

### Database connections remain open

**Symptom**: Connection warnings after shutdown

**Solutions**:
- Verify `cleanup_db_connections` is registered
- Ensure sessions are tracked when created
- Check for session leaks (not closed after use)
- Confirm database engine is disposed

### Cleanup callbacks not running

**Symptom**: State not saved, resources not cleaned

**Solutions**:
- Verify callbacks registered before shutdown
- Check for exceptions in callbacks (logged but don't stop cleanup)
- Ensure `shutdown()` is called in finally block
- Confirm async callbacks are properly awaited

## Future Enhancements

Potential improvements for future versions:

1. **Graceful degradation** - Gradually reduce task parallelism during shutdown
2. **Progress reporting** - Show which tasks are still running during wait
3. **Configurable callback order** - Priority-based cleanup execution
4. **Shutdown hooks** - Allow components to register for shutdown notification
5. **State persistence optimization** - Incremental state saving during operation
6. **Recovery on restart** - Resume interrupted tasks from saved state

## References

- **Implementation**: `src/aegis/utils/shutdown.py:22`
- **State Management**: `src/aegis/database/state.py:76`
- **Session Cleanup**: `src/aegis/database/session.py:89`
- **Configuration**: `src/aegis/config.py:52`
- **Unit Tests**: `tests/unit/test_shutdown.py`
- **Manual Tests**: `tests/manual_shutdown_test.py`
- **CLI Integration**: `src/aegis/cli.py:159` (do command), `src/aegis/cli.py:428` (work-on command)
