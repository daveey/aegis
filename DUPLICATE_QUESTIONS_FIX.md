# Duplicate Questions Bug Fix

**Date**: 2025-11-25
**Issue**: Multiple identical question tasks were being created in Asana (3 duplicates of "Question: How should Asana rich text formatting be implemented?")

## Root Cause

The duplicate questions bug had two root causes:

### 1. Race Condition in `work_on` Command
The `work_on` command checked for existing questions at the beginning of execution (cli.py:1106-1109), but:
- Multiple tasks could trigger the same question type
- Questions were created later in the execution flow (cli.py:1235-1259)
- No re-check happened right before creation
- If the command ran multiple times concurrently or sequentially, it could create duplicates

### 2. Claude Creating Duplicate Questions Directly
When executing tasks via `aegis do` or within `work_on`, Claude was instructed to:
- Create Question tasks directly via the Asana API
- No list of existing questions was provided in the prompt
- Claude couldn't know if a question already existed
- Each execution could create the same question again

## Fixes Applied

### Fix 1: Double-Check Before Creation (`work_on` command)

**Location**: `src/aegis/cli.py:1210-1222`

```python
# Fetch existing questions once for use in both question creation and task execution
console.print(f"\n[dim]Fetching existing question tasks...[/dim]")
current_tasks = await asyncio.to_thread(
    tasks_api.get_tasks_for_project,
    project["gid"],
    {"opt_fields": "name,gid,completed"}
)
existing_questions_now = {}
for task in current_tasks:
    task_dict = task if isinstance(task, dict) else task.to_dict()
    if task_dict.get("name", "").startswith("Question:") and not task_dict.get("completed", False):
        existing_questions_now[task_dict["name"]] = task_dict["gid"]
```

**Location**: `src/aegis/cli.py:1213-1218`

```python
# Double-check that question doesn't exist right before creating
question_name = f"Question: {q_details['question']}"
if question_name in existing_questions_now:
    console.print(f"  ⊙ Question already exists: {question_name}")
    q_details["task_gid"] = existing_questions_now[question_name]
    continue
```

**Benefits**:
- Fetches fresh list of questions right before creation
- Checks each question immediately before creating it
- Reuses existing question if found
- Prevents duplicates within same run by tracking created questions

### Fix 2: Provide Existing Questions to Claude (`aegis do` command)

**Location**: `src/aegis/cli.py:686-699`

```python
# Fetch existing question tasks to prevent duplicates
existing_questions_list = []
try:
    all_project_tasks = await fetch_with_retry(
        tasks_api.get_tasks_for_project,
        project["gid"],
        {"opt_fields": "name,gid,completed"}
    )
    for task in all_project_tasks:
        task_dict = task if isinstance(task, dict) else task.to_dict()
        if task_dict.get("name", "").startswith("Question:") and not task_dict.get("completed", False):
            existing_questions_list.append(task_dict["name"])
except Exception as e:
    logger.warning("failed_to_fetch_existing_questions", error=str(e))
```

**Location**: `src/aegis/cli.py:709-710, 1340-1341`

```python
if existing_questions_list:
    task_context += f"\n\nExisting Question Tasks (DO NOT CREATE DUPLICATES):\n" + "\n".join(f"  - {q}" for q in existing_questions_list)
```

**Updated Prompt** (`src/aegis/cli.py:719-723, 1351-1354`):

```
IMPORTANT: You are running in HEADLESS mode.

- Do not ask the user questions or wait for input
- If you need clarification, CHECK THE "Existing Question Tasks" LIST ABOVE FIRST
- Only create a NEW Question task if it doesn't already exist (exact name match required)
- Question task format: "Question: [specific question]" (must start with "Question: ")
- Use the Asana API to create question tasks and add them as dependencies to blocked tasks
```

**Benefits**:
- Claude sees all existing questions before creating new ones
- Explicit instruction to check for duplicates
- Requires exact name match to prevent similar-but-different questions
- Works for both `aegis do` and `work_on` execution paths

## Verification

Deleted 3 duplicate question tasks:
- Question: How should Asana rich text formatting be implemented? (GID: 1212155097925666)
- Question: How should Asana rich text formatting be implemented? (GID: 1212155900999432)
- Question: How should Asana rich text formatting be implemented? (GID: 1212155097675095)

Confirmed no remaining duplicates with test script.

## Testing

To test the fix:

```bash
# Run work_on multiple times - should not create duplicates
aegis work-on Aegis --dry-run

# Check for duplicates
python -c "
import asyncio
from aegis.asana.client import AsanaClient
from aegis.config import Settings
from collections import Counter

async def check():
    client = AsanaClient(Settings().asana_access_token)
    tasks = await client.get_tasks_from_project('1212085431574340')
    questions = [t.name for t in tasks if t.name.startswith('Question:') and not t.completed]
    duplicates = {n: c for n, c in Counter(questions).items() if c > 1}
    print('Duplicates:' if duplicates else 'No duplicates!', duplicates or '✓')

asyncio.run(check())
"
```

## Impact

- **work_on command**: Will no longer create duplicate questions when run multiple times
- **aegis do command**: Claude will check existing questions before creating new ones
- **Concurrent execution**: Questions are fetched fresh before creation to handle race conditions
- **User experience**: Cleaner Asana projects without duplicate question tasks

## Files Modified

- `src/aegis/cli.py` (lines 686-725, 1210-1264, 1340-1354)

## Related Issues

This fix also improves the overall question creation workflow by:
1. Making existing questions visible to Claude
2. Providing clearer instructions about when to create questions
3. Enabling question reuse across multiple tasks with the same blocker
