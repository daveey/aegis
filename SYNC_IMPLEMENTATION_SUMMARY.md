# Asana Sync Utility - Implementation Summary

**Date**: 2025-11-25
**Task**: Build Asana sync utility
**Status**: ✅ Complete

## Overview

Implemented a complete Asana synchronization utility that syncs projects and tasks from the configured portfolio into the local PostgreSQL database. The sync is idempotent and tracks last sync timestamps.

## Implementation Details

### 1. Added Portfolio API Support

**File**: `src/aegis/asana/client.py` (lines 865-910)

Added `get_projects_from_portfolio()` method to fetch all projects from a portfolio:

```python
async def get_projects_from_portfolio(self, portfolio_gid: str) -> list[AsanaProject]
```

- Uses retry logic with exponential backoff (3 attempts)
- Fetches project metadata: name, notes, archived, public, permalink_url, team, workspace
- Returns list of `AsanaProject` objects

### 2. Created Sync Module

**Directory**: `src/aegis/sync/`

Created new module with the following structure:
- `__init__.py` - Module exports
- `asana_sync.py` - Main sync implementation (294 lines)

### 3. Implemented Sync Functions

#### `sync_portfolio_projects()`
- Fetches all projects from portfolio
- Creates or updates projects in database
- Tracks `last_synced_at` timestamp for each project
- Updates `system_state.last_portfolio_sync_at`
- Returns list of synced `Project` objects

#### `sync_project_tasks()`
- Fetches all tasks for a given project
- Creates or updates tasks in database
- Syncs comprehensive task metadata:
  - Basic info: name, description, html_notes
  - Status: completed, completed_at
  - Dates: due_on, due_at, modified_at
  - Assignment: assignee_gid, assignee_name, assigned_to_aegis
  - Metadata: permalink_url, tags, custom_fields, num_subtasks
- Tracks `last_synced_at` timestamp for each task
- Updates `system_state.last_tasks_sync_at`
- Returns list of synced `Task` objects

#### `sync_all()`
- Convenience function to sync all projects and tasks
- Uses single database session for efficiency
- Skips archived projects
- Returns tuple of (projects, tasks)

### 4. Added CLI Command

**File**: `src/aegis/cli.py` (lines 244-309)

Added `aegis sync` command with the following features:

```bash
aegis sync                    # Sync all projects and tasks
aegis sync --projects-only    # Only sync projects, skip tasks
```

**Features**:
- Rich console output with progress indicators
- Detailed logging with structlog
- Error handling with rollback support
- Clear success/failure messages

### 5. Database Integration

**Existing Models Used**:
- `Project` (models.py:32-58) - Already had `last_synced_at` field
- `Task` (models.py:60-110) - Already had `last_synced_at` field
- `SystemState` (models.py:288-318) - Already had sync timestamp fields

**Session Management**:
- Uses existing `get_db_session()` context manager
- Proper transaction handling with commit/rollback
- Automatic session cleanup

## Testing Results

### Test 1: Initial Sync (Projects Only)
```bash
aegis sync --projects-only
```

**Result**: ✅ Success
- Created 3 projects: Aegis, Triptic, Agents
- Timestamps tracked in `system_state`

### Test 2: Full Sync (Projects + Tasks)
```bash
aegis sync
```

**Result**: ✅ Success
- Synced 3 projects
- Synced 39 tasks across projects:
  - Aegis: 37 tasks
  - Triptic: 2 tasks
  - Agents: 0 tasks

### Test 3: Idempotency Check
```bash
aegis sync  # Run again
```

**Result**: ✅ Success
- All projects marked as "updated" (not created)
- All tasks marked as "updated" (not created)
- Record counts unchanged: 3 projects, 39 tasks
- Timestamps updated correctly

### Database Verification
```sql
SELECT COUNT(*) FROM projects;  -- 3
SELECT COUNT(*) FROM tasks;     -- 39
SELECT last_portfolio_sync_at, last_tasks_sync_at FROM system_state;
-- Both timestamps present and current
```

## Key Features

### ✅ Idempotent Operations
- Re-running sync updates existing records instead of creating duplicates
- Uses `asana_gid` as unique identifier for matching

### ✅ Timestamp Tracking
- Project-level: `last_synced_at` per project
- Task-level: `last_synced_at` per task
- System-level: `last_portfolio_sync_at` and `last_tasks_sync_at`

### ✅ Comprehensive Data Sync
- All relevant project metadata
- All relevant task metadata including custom fields and tags
- Proper handling of nullable fields (assignee, dates, etc.)

### ✅ Error Handling
- Transaction rollback on errors
- Structured logging for debugging
- User-friendly error messages

### ✅ Performance
- Single database session per sync operation
- Bulk processing within transactions
- Async API calls for Asana

## Future Enhancements

### Answered Questions in Implementation

1. **Should we sync on a schedule or on-demand only?**
   - **Current**: On-demand only via `aegis sync` command
   - **Future**: Could add scheduled sync in orchestrator loop

2. **How often to sync (every 30s? 1 min? 5 min?)?**
   - **Current**: Manual invocation
   - **Future**: If scheduled, recommend:
     - Projects: Every 5-10 minutes (they change infrequently)
     - Tasks: Every 1-2 minutes (more dynamic)
     - Or use webhook-based incremental sync

### Potential Improvements

1. **Incremental Sync**
   - Use `modified_at` timestamps to only fetch changed tasks
   - Implement `modified_since` parameter in Asana API calls
   - Would significantly reduce API calls for large projects

2. **Webhook Integration**
   - Real-time sync triggered by Asana webhooks
   - Already have `Webhook` model defined (models.py:320-347)
   - Would eliminate need for polling

3. **Parallel Project Sync**
   - Sync multiple projects concurrently
   - Would speed up full portfolio sync

4. **Selective Sync**
   - `aegis sync --project <name>` to sync specific project
   - Useful for large portfolios

5. **Sync Statistics**
   - Track sync duration, API calls made, records created/updated
   - Add to `SystemState` or new `SyncLog` table

## Files Modified

1. `src/aegis/asana/client.py` - Added `get_projects_from_portfolio()` method
2. `src/aegis/cli.py` - Added `sync` command
3. `src/aegis/sync/__init__.py` - New module (5 lines)
4. `src/aegis/sync/asana_sync.py` - New sync implementation (294 lines)

## Files Not Modified (Used Existing)

1. `src/aegis/database/models.py` - Already had all necessary fields
2. `src/aegis/database/session.py` - Used existing session management
3. `src/aegis/config.py` - Used existing settings

## Acceptance Criteria

✅ **Can run `aegis sync` and see projects/tasks in DB**
- Command works and populates database correctly

✅ **Re-running sync updates existing records (idempotent)**
- Verified through testing - updates instead of duplicates

✅ **Tracks last sync time**
- Project-level, task-level, and system-level timestamps all working

## Usage Guide

### Basic Usage

```bash
# Sync everything (projects + tasks)
aegis sync

# Sync only projects (skip tasks)
aegis sync --projects-only

# Disable rich formatting (for scripts)
aegis sync --no-console
```

### Querying Synced Data

```sql
-- List all projects
SELECT asana_gid, name, archived, last_synced_at FROM projects;

-- List all tasks for a project
SELECT t.name, t.completed, t.assignee_name, t.last_synced_at
FROM tasks t
JOIN projects p ON t.project_id = p.id
WHERE p.name = 'Aegis';

-- Check sync status
SELECT last_portfolio_sync_at, last_tasks_sync_at
FROM system_state;
```

### Integration with Other Commands

The sync creates a local cache of Asana data that can be used by:
- Task prioritization algorithms
- Offline analysis
- Reporting and dashboards
- Faster query performance vs. repeated API calls

## Conclusion

Successfully implemented a complete Asana sync utility that meets all acceptance criteria. The implementation is:
- **Production-ready**: Proper error handling, logging, and transactions
- **Idempotent**: Safe to run repeatedly
- **Extensible**: Easy to add incremental sync, webhooks, or scheduling
- **Well-tested**: Verified through multiple test scenarios

The sync utility provides a solid foundation for future features that need access to Asana data without making repeated API calls.
