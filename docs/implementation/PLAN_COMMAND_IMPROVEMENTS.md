# Plan Command Improvements

## Summary

Updated the `aegis plan` command to make Claude think more carefully about task clarity and automatically create question tasks in Asana when clarification is needed. Question tasks are added as dependencies to the original tasks, blocking them until answered.

## Changes Made

### 1. Enhanced Task Consolidation Prompt (Lines 1548-1603)

**Previous behavior:**
- Claude would consolidate duplicate tasks
- Mentioned creating question tasks but wasn't specific about the process
- No emphasis on thorough analysis

**New behavior:**
- **STEP 1**: Thorough analysis of each task for clarity, ambiguities, missing requirements, technical decisions
- **STEP 2**: Create question tasks for any ambiguities with:
  - Clear title: "Question: [specific question]"
  - Detailed description including what needs clarification and why
  - Added as a dependency to the original task (blocking it)
  - Original task moved to "Waiting for Response"
  - Comment posted explaining the block
- **STEP 3**: Consolidate duplicates (existing functionality)
- **STEP 4**: Provide detailed summary of all actions

**Key improvements:**
- Structured step-by-step process
- Explicit instructions to add dependencies
- Emphasis on being thorough ("better to create a question than have implementation fail")
- Think carefully about each task

### 2. Enhanced Task Selection Prompt (Lines 1686-1732)

**Previous behavior:**
- Simple instruction to select N tasks
- Told Claude not to ask questions
- Would include unclear tasks in selection

**New behavior:**
- **STEP 1**: Analyze each candidate for clarity, requirements, ambiguities, dependencies, technical decisions
- **STEP 2**: Create question tasks for unclear candidates and don't include them in selection
- **STEP 3**: Select only truly ready tasks from clear candidates
- **STEP 4**: Return JSON array (can be shorter than target if tasks aren't ready)

**Key improvements:**
- Proactive identification of unclear tasks
- Permission to return fewer tasks if many need clarification
- Creates question tasks automatically rather than just skipping unclear tasks
- Focus on quality over quantity

## How It Works

### Question Task Creation

When Claude identifies an unclear task, it will:

1. **Create a question task** in Asana:
   ```
   Title: "Question: Should we use REST or GraphQL for the API?"
   Description:
   - Related task: "Build user API" (GID: 123456789)
   - Question: Which API architecture should we use?
   - Context: The task mentions building an API but doesn't specify...
   - Options: REST, GraphQL, gRPC
   ```

2. **Add dependency**: The question task becomes a dependency of the original task
   - Original task is now blocked until the question is answered
   - Dependency is visible in Asana UI

3. **Move to "Waiting for Response"**: Original task is moved out of "Ready to Implement"

4. **Post comment**: "Blocked: needs clarification - see [Question Task GID]"

### Workflow

```
┌─────────────────────────────────────────┐
│ User runs: aegis plan Aegis --target 5 │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│ Claude analyzes all "Ready" tasks       │
│ - Task A: Clear and ready ✓             │
│ - Task B: Unclear requirements ⚠️       │
│ - Task C: Duplicate of Task A           │
│ - Task D: Clear but needs decision ⚠️   │
└─────────────┬───────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────┐
│ Claude takes actions:                   │
│                                          │
│ 1. Creates question tasks:              │
│    - "Question: What format for Task B?"│
│    - "Question: REST or GraphQL for D?" │
│                                          │
│ 2. Adds dependencies:                   │
│    - Task B depends on Question 1       │
│    - Task D depends on Question 2       │
│                                          │
│ 3. Moves blocked tasks:                 │
│    - Task B → "Waiting for Response"    │
│    - Task D → "Waiting for Response"    │
│                                          │
│ 4. Consolidates duplicates:             │
│    - Task C merged into Task A          │
│                                          │
│ 5. Provides summary                     │
└─────────────────────────────────────────┘
```

## Example Usage

```bash
# Review and consolidate current ready tasks
aegis plan Aegis

# Ensure 5 tasks are ready (move from other sections if needed)
aegis plan Aegis --target 5

# Preview what would happen without making changes
aegis plan Aegis --dry-run

# Skip consolidation, only check task count
aegis plan Aegis --no-consolidate
```

## Benefits

1. **Prevents ambiguous tasks from being implemented**
   - Blocks unclear tasks until clarification is received
   - Creates structured questions for the team

2. **Automatic dependency management**
   - Question tasks become blockers in Asana
   - Clear visual indication of what's blocked

3. **Reduces implementation failures**
   - Tasks are only "ready" when they're truly ready
   - Technical decisions are identified upfront

4. **Better team communication**
   - Questions are specific and contextual
   - All clarifications tracked in Asana

5. **Quality over quantity**
   - Better to have 3 clear tasks than 5 ambiguous ones
   - Claude is encouraged to be thorough

## Testing

To test the improvements:

```bash
# Create some intentionally ambiguous tasks in Asana
# Example: "Add authentication" (which method? where? what flow?)

# Run plan command
aegis plan YourProject

# Verify Claude:
# - Identifies ambiguous tasks
# - Creates specific question tasks
# - Adds dependencies
# - Moves blocked tasks to "Waiting for Response"
# - Posts comments explaining blocks
```

## Future Enhancements

Potential improvements:
- [ ] Allow user to specify "clarification style" (verbose vs. concise questions)
- [ ] Track how often questions are needed per project (quality metric)
- [ ] Automatically assign question tasks to project owner
- [ ] Create question templates for common ambiguities
- [ ] Learn from past clarifications to reduce future questions

## Technical Details

### Files Modified
- `src/aegis/cli.py` (lines 1548-1603, 1686-1732)

### Key Prompt Changes
- Added explicit step-by-step analysis process
- Added PROJECT_GID to prompts for API access
- Emphasized thoroughness and quality over speed
- Structured output requirements (summary format)
- Added permission to return fewer tasks if needed

### API Operations Used
- Create task (for question tasks)
- Add dependencies (to block original tasks)
- Move task to section (to "Waiting for Response")
- Post comment (to explain blocks)
- Update task (for consolidations)
- Delete task (for duplicates)

---

**Last Updated**: 2025-11-25
