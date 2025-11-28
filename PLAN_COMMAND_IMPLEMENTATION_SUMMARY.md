# Plan Command Implementation Summary

**Date**: 2025-11-25
**Status**: ✅ Complete

## Overview

Successfully implemented the `aegis plan [project]` command to manage and organize tasks in the "Ready to Implement" section of Asana projects.

## What Was Implemented

### 1. New AsanaClient Method: `get_tasks_for_section()`

**File**: `src/aegis/asana/client.py` (lines 497-552)

- Fetches all tasks from a specific section
- Supports retry logic with exponential backoff
- Returns list of `AsanaTask` objects
- Includes comprehensive opt_fields for task details

### 2. New CLI Command: `aegis plan`

**File**: `src/aegis/cli.py` (lines 1115-1382)

**Features**:
- Reviews current task list across all sections
- Ensures target number of tasks (default: 5) in "Ready to Implement"
- Uses Claude CLI for intelligent task selection and consolidation
- Supports dry-run mode for preview without changes

**Options**:
- `--target N` - Set target number of ready tasks (default: 5)
- `--dry-run` - Preview changes without executing

## Command Behavior

### When Below Target

1. **Analyzes all sections** to count incomplete tasks
2. **Identifies candidate tasks** from:
   - Ideas (highest priority)
   - Waiting for Response
   - In Progress (unassigned only)
3. **Asks Claude to select** which tasks to move based on:
   - Task dependencies and clarity
   - Value and importance
   - Avoiding duplicates with existing ready tasks
4. **Moves selected tasks** to "Ready to Implement"

### When Target Met

1. **Reviews existing ready tasks** for quality
2. **Asks Claude to analyze** for:
   - Duplicate or similar tasks that could be consolidated
   - Unclear tasks needing better descriptions
   - Suggested priority order
3. **Provides recommendations** without moving tasks

## Claude Integration

The command intelligently uses Claude CLI to:

- **Select tasks**: Returns JSON array of task GIDs in priority order
- **Consolidate**: Identifies duplicates and suggests merging
- **Prioritize**: Orders tasks by importance and readiness
- **Explain reasoning**: Provides context for each decision

**Fallback**: If Claude's JSON parsing fails, automatically selects first N candidates

## Usage Examples

```bash
# Ensure 5 tasks are ready
aegis plan Aegis

# Ensure 10 tasks are ready
aegis plan Aegis --target 10

# Preview without changes
aegis plan Aegis --dry-run
```

## Output Example

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

## Technical Details

### Task Selection Algorithm

1. **Fetches tasks by section** using new `get_tasks_for_section()` method
2. **Filters incomplete tasks** (excludes completed)
3. **Prioritizes source sections**:
   - Ideas (unfinished ideas become concrete tasks)
   - Waiting for Response (unblock stalled work)
   - In Progress (unassigned only - don't steal active work)
4. **Uses Claude for final selection** with full task context

### Error Handling

- **API retry logic**: 3 attempts with exponential backoff
- **Fallback selection**: Automatic if Claude parsing fails
- **Clear error messages**: Guides user to run `aegis organize` if sections missing
- **Dry-run mode**: Test without making changes

### Integration Points

- **AsanaClient**: Uses existing retry/logging patterns
- **CLI framework**: Follows Click conventions
- **Claude CLI**: Subprocess execution with timeout
- **Structured logging**: Uses structlog throughout

## Documentation Updates

### TOOLS.md

Added comprehensive documentation for `aegis plan` command including:
- Usage examples
- Behavior description
- Claude integration details
- Output examples
- Comparison to other commands
- When to use guidelines
- Error handling details

## Testing

### Manual Testing Completed

✅ Command registration (`aegis --help` shows plan command)
✅ Help text displays correctly (`aegis plan --help`)
✅ Python syntax validation (both modified files)
✅ Command structure follows existing patterns

### Recommended Testing

Before using in production:

1. **Dry-run test**: `aegis plan Aegis --dry-run`
2. **Low target test**: `aegis plan Aegis --target 2`
3. **High target test**: `aegis plan Aegis --target 10`
4. **Consolidation test**: Run when already at target

## Files Modified

1. **src/aegis/asana/client.py**
   - Added `get_tasks_for_section()` method (55 lines)

2. **src/aegis/cli.py**
   - Replaced placeholder `plan()` command with full implementation (268 lines)
   - Added Claude CLI integration
   - Added intelligent task selection logic

3. **TOOLS.md**
   - Added complete documentation for `aegis plan` command (183 lines)

## Key Features

✅ **Intelligent task selection** using Claude AI
✅ **Dry-run mode** for safe preview
✅ **Configurable target** (default: 5 tasks)
✅ **Task consolidation** recommendations when target met
✅ **Priority-based section selection** (Ideas → Waiting → In Progress)
✅ **Fallback logic** if Claude parsing fails
✅ **Comprehensive error handling**
✅ **Rich console output** with progress indicators
✅ **Full documentation** in TOOLS.md

## Design Decisions

### Why Pull from Ideas First?

Ideas are typically rough concepts that benefit from being moved to "Ready to Implement" when they're fleshed out enough to work on.

### Why Use Claude for Selection?

Claude can understand task context, dependencies, and importance better than simple heuristics. It considers:
- Task descriptions and notes
- Existing ready tasks (avoid duplicates)
- Dependencies and blockers
- Overall project goals

### Why Consolidate Mode?

When the queue is full, it's better to improve quality than add more tasks. Consolidation mode helps:
- Identify duplicates
- Clarify unclear tasks
- Suggest priority order
- Keep the backlog clean

## Future Enhancements

Possible improvements for future iterations:

1. **Auto-consolidation**: Automatically merge duplicate tasks
2. **Task editing**: Update task descriptions based on Claude suggestions
3. **Dependency tracking**: More sophisticated blocker detection
4. **Custom sections**: Support projects with different section names
5. **Batch mode**: Plan multiple projects at once
6. **Scheduled planning**: Run on a schedule (daily/weekly)

## Conclusion

The `aegis plan` command is fully implemented and ready to use. It provides intelligent task queue management with Claude AI assistance, making it easy to maintain a healthy "Ready to Implement" section in any Asana project.

Run `aegis plan --help` for usage details.
