# Claude CLI Logging Implementation

**Date**: 2025-11-25
**Feature**: Log file creation for all Claude CLI executions with web dashboard integration

## Overview

Implemented comprehensive logging for all Claude CLI subprocess executions in the orchestrator. Each task execution now writes its complete session output to a unique log file, and the web dashboard provides clickable log viewing with a modal interface.

## Implementation

### 1. Orchestrator Subprocess Logging

**Modified**: `src/aegis/orchestrator/main.py` (lines 953-1012)

**Changes**:
- Creates unique log file for each task execution: `logs/task_{gid}_{timestamp}.log`
- Redirects Claude CLI stdout/stderr to log file in real-time
- Writes structured log header with task metadata
- Writes log footer with completion timestamp and exit code
- Updates display with log file path before execution starts
- Reads log file back to store in database (for backwards compatibility)

**Log File Format**:
```
=== Aegis Task Execution Log ===
Task: [task name]
Task GID: [gid]
Started: [ISO timestamp]
Working Directory: [path]
==================================================

[Claude CLI output here]

==================================================
Completed: [ISO timestamp]
Exit Code: [code]
```

**Code Changes**:
```python
# Create unique log file for this task
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
log_file = logs_dir / f"task_{task.gid}_{timestamp}.log"

# Update display with log file path before starting
self._update_task_in_display(
    task.gid,
    "running",
    log_file=str(log_file)
)

# Open log file for writing
with open(log_file, "w") as log_fh:
    # Write header
    log_fh.write(f"=== Aegis Task Execution Log ===\n")
    log_fh.write(f"Task: {task.name}\n")
    log_fh.write(f"Task GID: {task.gid}\n")
    log_fh.write(f"Started: {datetime.now().isoformat()}\n")
    log_fh.write(f"Working Directory: {working_dir}\n")
    log_fh.write(f"=" * 50 + "\n\n")
    log_fh.flush()

    # Run Claude CLI with output redirected to log file
    process = subprocess.Popen(
        ["claude", "--dangerously-skip-permissions", task_context],
        cwd=working_dir,
        stdout=log_fh,
        stderr=subprocess.STDOUT,  # Merge stderr into stdout
        text=True,
    )

    # ... process management ...

    # Write footer
    log_fh.write(f"\n\n{'=' * 50}\n")
    log_fh.write(f"Completed: {datetime.now().isoformat()}\n")
    log_fh.write(f"Exit Code: {process.returncode}\n")

# Read log for database storage
with open(log_file, "r") as log_fh:
    output = log_fh.read()
```

### 2. Web Dashboard Updates

**Modified**: `src/aegis/orchestrator/web.py`

#### A. Added Modal CSS (lines 385-465)

**Styles Added**:
- `.log-preview` - Made clickable with cursor pointer and hover effect
- `.log-preview-hint` - Hint text showing "Click to view full log"
- `.modal` - Full-screen modal overlay
- `.modal-content` - Modal container with flex layout
- `.modal-header` - Modal header with title and close button
- `.modal-close` - Close button with hover effect
- `.modal-body` - Scrollable modal body
- `.modal-log` - Monospace log display area

#### B. Updated Agent Card HTML (lines 840-845)

**Changes**:
- Added `onclick` handler to log preview: `onclick="showFullLog(...)"`
- Added hint text below log preview
- Passes task GID and name to modal function

```html
<div class="log-preview" id="log-${agent.task_gid}" onclick="showFullLog('${agent.task_gid}', '${escapeHtml(agent.task_name)}')">
    <span class="pulse">Loading log...</span>
</div>
<div class="log-preview-hint">Click to view full log</div>
```

#### C. Added Modal HTML (lines 623-634)

**Structure**:
```html
<div class="modal" id="logModal">
    <div class="modal-content">
        <div class="modal-header">
            <div class="modal-title" id="modalTitle">Full Log</div>
            <button class="modal-close" onclick="closeLogModal()">&times;</button>
        </div>
        <div class="modal-body">
            <div class="modal-log" id="modalLog">Loading...</div>
        </div>
    </div>
</div>
```

#### D. Added JavaScript Functions (lines 914-958)

**Functions**:
1. `showFullLog(taskGid, taskName)` - Opens modal and fetches full log
2. `closeLogModal()` - Closes the modal
3. Event listeners for Escape key and clicking outside modal

```javascript
async function showFullLog(taskGid, taskName) {
    const modal = document.getElementById('logModal');
    const modalTitle = document.getElementById('modalTitle');
    const modalLog = document.getElementById('modalLog');

    // Set title
    modalTitle.textContent = `Log: ${taskName}`;

    // Show modal
    modal.classList.add('active');

    // Load full log
    modalLog.textContent = 'Loading full log...';
    try {
        const response = await fetch(`/api/logs/${taskGid}`);
        const data = await response.json();
        if (data.error) {
            modalLog.textContent = `Error: ${data.error}`;
        } else {
            modalLog.textContent = data.log || '(No output yet)';
        }
    } catch (error) {
        modalLog.textContent = `Failed to load log: ${error.message}`;
    }
}

function closeLogModal() {
    const modal = document.getElementById('logModal');
    modal.classList.remove('active');
}

// Close modal on escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeLogModal();
    }
});

// Close modal when clicking outside
document.getElementById('logModal').addEventListener('click', (e) => {
    if (e.target.id === 'logModal') {
        closeLogModal();
    }
});
```

### 3. Display Integration

The `OrchestratorDisplay` class already supported the `log_file` parameter:
- `add_task()` accepts `log_file` parameter
- `update_task_status()` accepts `log_file` parameter
- Stores log file path in `active_tasks` dict
- Web dashboard reads from this dict via `_get_agents_data()`

**No changes needed** - the display layer was already prepared for this feature.

### 4. API Endpoint

The `/api/logs/{task_gid}` endpoint already existed in web.py:
- Reads log file from display's `active_tasks` dict
- Returns last 1000 lines (to prevent memory issues)
- Handles missing files gracefully

**No changes needed** - the API was already functional.

## Usage

### Running the Orchestrator

```bash
# Start orchestrator with web dashboard (default)
aegis start Aegis

# Web dashboard will be available at:
# http://127.0.0.1:8000
```

### Viewing Logs

**In Web Dashboard**:
1. Navigate to http://127.0.0.1:8000
2. Scroll to "Active Agents" section
3. Each running agent shows a log preview (last 20 lines, auto-refreshing)
4. Click on the log preview to view full log in modal
5. Modal shows complete log with scrolling
6. Press Escape or click outside to close modal

**In File System**:
```bash
# View all task logs
ls -lh logs/task_*.log

# View specific log
cat logs/task_1212155069373058_20251125_200948.log

# Tail a running log
tail -f logs/task_1212155069373058_20251125_200948.log
```

### Log File Naming

Format: `logs/task_{gid}_{timestamp}.log`

Example: `logs/task_1212155069373058_20251125_200948.log`
- `task_` - Prefix indicating task execution log
- `1212155069373058` - Asana task GID
- `20251125_200948` - Timestamp (YYYYMMDD_HHMMSS)
- `.log` - Extension

## Benefits

### 1. Complete Session History
- Every Claude CLI execution is fully logged
- Logs persist after task completion
- Can debug issues after the fact

### 2. Real-Time Monitoring
- Web dashboard shows live log preview (last 20 lines)
- Preview auto-refreshes every 2 seconds
- Can watch task execution in progress

### 3. Full Log Access
- Click log preview to view complete log
- Modal interface with scrolling
- No need to SSH or use terminal

### 4. Structured Logging
- Consistent log format with headers and footers
- Includes task metadata (name, GID, working directory)
- Timestamps for start and completion
- Exit code for debugging failures

### 5. File System Integration
- Logs stored in standard `logs/` directory
- Easy to archive, backup, or analyze
- Can be processed by log analysis tools

## Testing

**Test Script**: `test_log_files.py`

```bash
# Run test
uv run python test_log_files.py
```

**What the test does**:
1. Creates orchestrator with web dashboard
2. Runs for 45 seconds
3. Polls and executes tasks
4. Creates log files for each execution
5. Lists all log files with previews
6. Web dashboard is available during test

**Expected Results**:
- ✅ Log files created in `logs/` directory
- ✅ Log files have correct naming format
- ✅ Log files contain task execution output
- ✅ Web dashboard shows log files
- ✅ Clicking log preview opens modal
- ✅ Modal shows full log content

## Technical Details

### Subprocess Execution Changes

**Before**:
```python
process = subprocess.Popen(
    ["claude", "--dangerously-skip-permissions", task_context],
    cwd=working_dir,
    stdout=subprocess.PIPE,  # Captured in memory
    stderr=subprocess.PIPE,  # Captured in memory
    text=True,
)
stdout, stderr = process.communicate()
output = stdout + "\n\nSTDERR:\n" + stderr
```

**After**:
```python
log_file = logs_dir / f"task_{task.gid}_{timestamp}.log"
with open(log_file, "w") as log_fh:
    # Write header
    log_fh.write("=== Aegis Task Execution Log ===\n")
    # ...

    process = subprocess.Popen(
        ["claude", "--dangerously-skip-permissions", task_context],
        cwd=working_dir,
        stdout=log_fh,  # Written to file
        stderr=subprocess.STDOUT,  # Merged with stdout
        text=True,
    )
    process.wait()

    # Write footer
    log_fh.write(f"Exit Code: {process.returncode}\n")

# Read back for database
with open(log_file, "r") as log_fh:
    output = log_fh.read()
```

### Web Dashboard Flow

1. **Task Execution Starts**:
   - Orchestrator creates log file
   - Updates display with `log_file` path
   - Starts Claude CLI subprocess writing to file

2. **Display Updates**:
   - Display stores log file path in `active_tasks` dict
   - Web dashboard fetches agent data via `/api/agents`
   - Response includes `log_file` for each active agent

3. **Log Preview**:
   - Frontend fetches log via `/api/logs/{task_gid}`
   - Shows last 20 lines in preview area
   - Auto-refreshes every 2 seconds

4. **Full Log View**:
   - User clicks log preview
   - `showFullLog()` opens modal
   - Fetches complete log via `/api/logs/{task_gid}`
   - Displays in scrollable modal

### Performance Considerations

- **File I/O**: Minimal overhead - single write stream per task
- **Log Size**: Full logs read when needed, preview shows last 20 lines
- **Memory**: Logs written to disk, not held in memory
- **Concurrent Tasks**: Each task gets unique log file, no conflicts
- **Disk Space**: Log files accumulate - consider rotation/archiving

### Future Enhancements

Potential improvements:
- [ ] Log rotation/archiving policy
- [ ] Download log file button
- [ ] Search/filter log content
- [ ] Syntax highlighting for log output
- [ ] Real-time streaming (WebSocket-based)
- [ ] Log aggregation across tasks
- [ ] Compress old logs
- [ ] Delete logs after X days

## Files Modified

1. **src/aegis/orchestrator/main.py**
   - Updated subprocess execution (lines 953-1012)
   - Added log file creation and writing
   - Redirected stdout/stderr to file

2. **src/aegis/orchestrator/web.py**
   - Added modal CSS (lines 385-465)
   - Updated agent card HTML (lines 840-845)
   - Added modal HTML structure (lines 623-634)
   - Added JavaScript functions (lines 914-958)

## Files Created

1. **test_log_files.py**
   - Test script for log file creation
   - Verifies orchestrator creates logs
   - Checks web dashboard integration

2. **CLAUDE_CLI_LOGGING_IMPLEMENTATION.md** (this file)
   - Complete documentation
   - Implementation details
   - Usage guide

## Summary

Successfully implemented comprehensive logging for all Claude CLI executions with:
- ✅ Unique log file per task execution
- ✅ Structured log format with metadata
- ✅ Real-time writing during execution
- ✅ Web dashboard integration
- ✅ Log preview with auto-refresh
- ✅ Clickable full log view in modal
- ✅ Keyboard shortcuts (Escape to close)
- ✅ Complete session history
- ✅ File system persistence

All Claude CLI sessions now write to log files, and the web dashboard provides an intuitive interface for viewing both live and historical logs.
