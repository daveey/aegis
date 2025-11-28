# Orchestrator Display Fix

## Problem

The `aegis start` command was running the orchestrator successfully - fetching tasks, queueing them, and dispatching them for execution. However, the Rich Live display was not visible to users because structlog output to stdout/stderr was interfering with the Rich display rendering.

## Root Cause

1. The Rich Live display was set to `screen=False`, meaning it updates in-place
2. Structlog was outputting to stdout/stderr at the same time
3. The log output was overwriting or pushing the display off-screen
4. Users couldn't see the active tasks table or orchestrator status

## Solution

### Changes Made

1. **Enabled Alternate Screen Mode** (`display.py:245`)
   - Changed `screen=False` to `screen=True`
   - This makes the display use alternate screen buffer, separating it from logs

2. **Redirected Logs to File** (`orchestrator/main.py:266-290`)
   - Reconfigured structlog to write to `logs/orchestrator_{pid}.log`
   - Uses JSON format for easy parsing
   - Logs no longer interfere with the display

3. **Added Startup Message** (`orchestrator/main.py:294-297`)
   - Shows PID and log file location before entering live display
   - Provides clear feedback that orchestrator has started

4. **Cleaned Up Debug Output**
   - Removed debug print statements that were added during investigation
   - All logging now goes through structlog to the log file

### Files Modified

- `src/aegis/orchestrator/display.py` - Changed `screen` parameter to `True`
- `src/aegis/orchestrator/main.py` - Added log redirection and startup message

## Testing

To test the fix:

```bash
# Start the orchestrator
aegis start Aegis

# You should see:
# 1. Startup message with PID and log file location
# 2. Rich Live display with:
#    - Orchestrator status (running/stopped)
#    - Statistics (dispatched/completed/failed)
#    - Active tasks table
# 3. Display updates every 0.5 seconds

# Monitor logs in another terminal:
tail -f logs/orchestrator_*.log | jq .

# Stop with Ctrl+C for graceful shutdown
```

## Expected Behavior

### Before Fix
- Orchestrator runs but display is not visible
- Logs are mixed with display attempts
- User has no visibility into active tasks

### After Fix
- Clean Rich Live display in alternate screen
- Clear status showing:
  - Orchestrator PID and status
  - Last poll time
  - Active task count
  - Task execution progress
- Logs written to file (shown at startup)
- Ctrl+C triggers graceful shutdown

## Additional Notes

- Log files are created in `logs/orchestrator_{pid}.log`
- Log format is JSON for easy parsing
- Display uses alternate screen (press Ctrl+C to exit and see previous output)
- First poll happens immediately (no 30s wait)
- Tasks are dispatched as soon as they're queued (if capacity available)

## Verification

Run the orchestrator and verify:
- [ ] Startup message shows with PID and log file
- [ ] Rich display appears in alternate screen
- [ ] Active tasks section shows running tasks
- [ ] Statistics update in real-time
- [ ] Last poll time updates every 30 seconds
- [ ] Ctrl+C stops gracefully
- [ ] Log file contains JSON-formatted events
