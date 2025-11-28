# Question Task Auto-Completion

**Feature**: Automatic completion of answered Question tasks
**Added**: 2025-11-25
**Command**: `aegis work-on`

---

## Overview

When you unassign yourself from a Question task in Asana, the next time `aegis work-on` runs, it will automatically:
- Mark the task as complete
- Move it to the "Answered" section
- Remove it from the active work queue

This streamlines the workflow by eliminating manual task completion steps.

---

## How to Use

### Step 1: Question is Created

When Aegis encounters a blocker, it creates a Question task and assigns it to you:

```
Question: PostgreSQL Setup
Assigned to: David
Status: Incomplete
```

### Step 2: You Answer the Question

1. Read the question in Asana
2. Add your answer as a comment
3. Take any necessary action (e.g., start PostgreSQL)
4. **Unassign yourself** from the task (leave it incomplete)

### Step 3: Automatic Completion

Next time `aegis work-on` runs:

```bash
$ aegis work-on Aegis

Analyzing Aegis project...
✓ Found project: Aegis (GID: 1212085431574340)

Fetching all tasks...
Found 1 answered Question task(s) to complete...
  • Completing: Question: PostgreSQL Setup
    ✓ Marked complete and moved to Answered

✓ Found 5 incomplete unassigned tasks
```

The Question task is now:
- ✅ Marked as complete
- 📁 Moved to "Answered" section
- 🔓 No longer blocking dependent tasks

---

## Detection Logic

A task is considered "answered" if ALL of these are true:

1. ✅ Task name starts with "Question:"
2. ✅ Task is incomplete (not marked done)
3. ✅ Task is unassigned (no assignee)

**Example: Tasks that ARE auto-completed**
- `Question: PostgreSQL Setup` - incomplete, unassigned ✅
- `Question: API Key Location` - incomplete, unassigned ✅

**Example: Tasks that are NOT auto-completed**
- `Question: Database Schema` - incomplete, still assigned to David ❌ (still working on it)
- `Question: Error Handling` - already completed ❌ (already done)
- `Task: Implement feature` - incomplete, unassigned ❌ (not a Question task)

---

## Benefits

### For Users
- **Less Manual Work**: Don't need to mark Question tasks complete
- **Simpler Workflow**: Just unassign = answered
- **Cleaner Projects**: Answered questions automatically archived

### For Aegis
- **Automatic Unblocking**: Completed questions unblock dependent tasks
- **Better Organization**: Answered section stays current
- **Audit Trail**: All questions preserved in "Answered" section

---

## Integration with Workflow

### Question Creation Flow

```
Aegis detects blocker
       ↓
Creates "Question: Topic" task
       ↓
Assigns to user (David)
       ↓
User reads and answers
       ↓
User unassigns themselves
       ↓
Next work-on run: Auto-complete + Move to Answered
       ↓
Dependent tasks become unblocked
```

### Section Flow

```
Question Created → Waiting for Response (assigned to user)
                          ↓
User unassigns → Next work-on run
                          ↓
           Auto-completed → Answered (complete)
```

---

## Error Handling

### If Completion Fails

The system handles errors gracefully:

```
Found 1 answered Question task(s) to complete...
  • Completing: Question: PostgreSQL Setup
    ⚠ Failed to complete: API rate limit exceeded
```

- **Continues processing** other tasks
- **Logs warning** for troubleshooting
- **Retries** on next work-on run

### If "Answered" Section Missing

If the project doesn't have an "Answered" section:
- Task is marked complete
- Warning is logged
- Task stays in current section

**Fix**: Run `aegis organize Aegis` to create standard sections

---

## Examples

### Example 1: Single Question

**Before work-on:**
```
Tasks:
  ✓ Question: PostgreSQL Setup (incomplete, unassigned)
  • Implement database layer (incomplete, unassigned)
  • Add API endpoints (incomplete, unassigned)
```

**After work-on:**
```
Found 1 answered Question task(s) to complete...
  • Completing: Question: PostgreSQL Setup
    ✓ Marked complete and moved to Answered

✓ Found 2 incomplete unassigned tasks
```

**Result:**
- Question marked complete
- Question in "Answered" section
- 2 regular tasks ready to work on

### Example 2: Multiple Questions

**Before work-on:**
```
Tasks:
  • Question: PostgreSQL Setup (incomplete, unassigned)
  • Question: API Key Location (incomplete, unassigned)
  • Question: Redis Configuration (incomplete, assigned to David)
  • Implement feature (incomplete, unassigned)
```

**After work-on:**
```
Found 2 answered Question task(s) to complete...
  • Completing: Question: PostgreSQL Setup
    ✓ Marked complete and moved to Answered
  • Completing: Question: API Key Location
    ✓ Marked complete and moved to Answered

✓ Found 1 incomplete unassigned tasks
```

**Note**: The third question wasn't auto-completed because it's still assigned to David (still working on it).

---

## Tips

### Best Practices

1. **Answer in Comments**: Always add your answer as a comment before unassigning
2. **Complete Actions First**: Take any required actions before unassigning
3. **Clear Answers**: Provide clear, actionable answers for audit trail
4. **Unassign = Done**: Only unassign when you've fully answered

### Common Patterns

**Pattern 1: Simple Answer**
```
Comment: "PostgreSQL is already running locally on port 5432.
          You can proceed with the database tasks."
Action: Unassign
```

**Pattern 2: Action Required**
```
Comment: "I've started PostgreSQL with: brew services start postgresql@16
          Database 'aegis' created and ready."
Action: Unassign
```

**Pattern 3: Needs More Info**
```
Comment: "Can you provide more details about the specific error?"
Action: Keep assigned (still discussing)
```

---

## Troubleshooting

### Question Not Auto-Completed

**Symptom**: Question task still shows as incomplete

**Check**:
1. ✅ Does task name start with "Question:"?
2. ✅ Is task marked incomplete in Asana?
3. ✅ Is task unassigned (no assignee)?
4. ✅ Did you run `aegis work-on` after unassigning?

### Auto-Completed Too Early

**Symptom**: Question was completed before you answered

**Cause**: Task was unassigned prematurely

**Prevention**:
- Keep task assigned while working on answer
- Only unassign when fully answered

### Question Not Moved to Answered

**Symptom**: Task marked complete but in wrong section

**Cause**: "Answered" section doesn't exist

**Fix**: Run `aegis organize Aegis` to create standard sections

---

## Related Documentation

- [Shutdown Handling](./SHUTDOWN_HANDLING.md) - Graceful shutdown for work-on
- [Prioritization](./PRIORITIZATION.md) - Task prioritization algorithm
- [Operator Guide](./OPERATOR_GUIDE.md) - Complete guide for operators

---

## Technical Details

### Implementation

**File**: `src/aegis/cli.py`
**Location**: Lines 979-1017 in `work_on()` command
**Method Used**: `AsanaClient.complete_task_and_move_to_answered()`

### Detection Algorithm

```python
answered_questions = [
    task for task in tasks_list
    if (
        not task.get("completed") and        # Not already done
        not task.get("assignee") and         # Unassigned (answered)
        task.get("name", "").startswith("Question:")  # Is a Question
    )
]
```

### Completion Process

```python
for question_task in answered_questions:
    # 1. Mark complete
    await asana_client.update_task(
        task_gid,
        AsanaTaskUpdate(completed=True)
    )

    # 2. Move to Answered section
    await asana_client.move_task_to_section(
        task_gid,
        project_gid,
        answered_section_gid
    )
```

---

## Changelog

**2025-11-25**: Initial implementation
- Auto-detection of answered questions
- Automatic completion and section movement
- Console feedback and error handling

---

**Questions about this feature?** Check the implementation summary at `QUESTION_AUTO_COMPLETE_SUMMARY.md`
