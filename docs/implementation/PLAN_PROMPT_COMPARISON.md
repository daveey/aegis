# Plan Command Prompt Comparison

## Before vs After

### Consolidation Prompt (when tasks >= target)

#### BEFORE (Old Prompt)
```
Your task:
1. Identify duplicate or very similar tasks that should be consolidated
2. For each consolidation opportunity, update the Asana tasks directly
3. If you need clarification, CREATE A NEW QUESTION TASK
4. Provide a summary

Begin consolidating now.
```

#### AFTER (New Prompt)
```
Your task: CAREFULLY review each task and identify issues that would block implementation.

STEP 1 - ANALYZE EACH TASK THOROUGHLY:
For each task, think carefully about:
- Is the task description clear and specific enough to implement?
- Are there multiple ways to interpret this task?
- What technical decisions need to be made?
- Are there missing requirements?
- Is this actually 2-3 separate tasks?
- Are there obvious duplicates?
- Does this have unstated dependencies?

STEP 2 - CREATE QUESTION TASKS FOR AMBIGUITIES:
For any task that has unclear requirements:
1. Create a NEW question task: "Question: [specific question]"
2. In description include:
   - Which task it relates to (name + GID)
   - What specifically needs clarification
   - Why this is needed for implementation
   - Options or context to help answer
3. Add question task as DEPENDENCY (original is blocked)
4. Move original to "Waiting for Response"
5. Post comment: "Blocked: needs clarification - see [Question GID]"

STEP 3 - CONSOLIDATE DUPLICATES:
[same as before]

STEP 4 - PROVIDE SUMMARY:
List all actions with specifics:
- Question tasks created (titles + GIDs)
- Dependencies added (which blocks which)
- Tasks consolidated (which into which)
- Tasks moved to "Waiting for Response"

Be THOROUGH - better to create a question than have implementation fail.
Think step-by-step for each task.
```

**Key differences:**
- ❌ Generic "think about it" → ✅ Specific analysis questions
- ❌ Vague instructions → ✅ Numbered steps with details
- ❌ "Create question task" → ✅ Exact format, dependency process
- ❌ Brief summary → ✅ Detailed summary with all GIDs
- ❌ No emphasis → ✅ "Be THOROUGH" + "Think step-by-step"

---

### Selection Prompt (when tasks < target)

#### BEFORE (Old Prompt)
```
Select N most important/ready tasks from candidates.

Please:
1. Select the N most important/ready tasks
2. Consider dependencies, clarity, and value
3. Avoid duplicates

Respond ONLY with JSON array:
["gid1", "gid2", "gid3"]

IMPORTANT: If you need clarification, DO NOT ASK QUESTIONS.
Instead, make your best judgment.
```

#### AFTER (New Prompt)
```
STEP 1 - ANALYZE EACH CANDIDATE CAREFULLY:
For each candidate task, consider:
- Is the task description clear and actionable?
- Are requirements well-defined?
- Are there ambiguities that would block implementation?
- Does it have implied dependencies?
- What technical choices/architectural decisions are needed?

STEP 2 - CREATE QUESTION TASKS FOR UNCLEAR CANDIDATES:
If a candidate is unclear or ambiguous:
- CREATE question task: "Question: [specific question]"
- Add as DEPENDENCY to unclear task (blocks it)
- Move original to "Waiting for Response"
- Do NOT include that task in selection below

STEP 3 - SELECT READY TASKS:
From remaining CLEAR candidates:
1. Select N most important tasks
2. Prioritize tasks that:
   - Have clear requirements and acceptance criteria
   - Don't duplicate existing ready tasks
   - Provide high value or unblock other work
   - Don't require unmade architectural decisions

STEP 4 - RESPOND WITH SELECTION:
Respond ONLY with JSON array:
["gid1", "gid2", "gid3"]

IMPORTANT: Be selective - only truly ready tasks.
If fewer than N are ready (due to ambiguities), that's FINE.
Create question tasks for unclear ones and return shorter array.
```

**Key differences:**
- ❌ "Don't ask questions" → ✅ "Create question tasks proactively"
- ❌ "Make best judgment" → ✅ "Block unclear tasks until answered"
- ❌ Must return exactly N → ✅ Can return fewer if tasks unclear
- ❌ No analysis structure → ✅ Explicit analysis criteria
- ❌ Implicit quality → ✅ Explicit "only truly ready tasks"

---

## Impact Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Task clarity** | Might include unclear tasks | Only includes clear tasks |
| **Questions** | Discouraged | Encouraged & automated |
| **Dependencies** | Not mentioned | Automatically added |
| **Quality bar** | Implicit | Explicit ("truly ready") |
| **Think process** | Unstructured | Step-by-step |
| **Blocking** | None | Unclear tasks blocked |
| **Flexibility** | Must return N tasks | Can return < N if needed |

## Example Scenarios

### Scenario 1: Ambiguous Authentication Task

**Task**: "Add authentication to the app"

#### Before:
- Claude would likely select it as "important"
- Task moves to Ready to Implement
- Developer starts work, realizes it's unclear
- Has to ask: JWT or sessions? Where? What flow?

#### After:
- Claude analyzes: Multiple ways to interpret this
- Creates: "Question: What authentication method should we use?"
  - Options: JWT, sessions, OAuth
  - Where: Frontend only or full-stack?
  - What flow: Login/signup/forgot password?
- Adds dependency: Auth task blocked by question
- Moves auth task to "Waiting for Response"
- Returns shorter array (doesn't include auth task)

### Scenario 2: Well-Defined Task

**Task**: "Implement user login form with email/password using existing auth service"

#### Before & After (same result):
- Claude recognizes: Clear, specific, ready
- Includes in selection
- Moves to Ready to Implement
- Developer can start immediately

### Scenario 3: Duplicate Tasks

**Task A**: "Add dark mode toggle"
**Task B**: "Implement dark theme switcher"

#### Before & After (same result):
- Claude recognizes duplicates
- Consolidates into one task
- Posts comment explaining merge
- Continues with selection

---

## Testing the Improvements

```bash
# Test 1: Create intentionally ambiguous tasks
# In Asana, create:
# - "Add authentication"
# - "Build the API"
# - "Improve performance"

# Run plan
aegis plan YourProject --target 5

# Expected result:
# - 3 question tasks created
# - Original tasks moved to "Waiting for Response"
# - Dependencies added
# - Fewer than 5 tasks moved to Ready (only clear ones)
# - Comments posted explaining blocks

# Test 2: Dry run to see what would happen
aegis plan YourProject --dry-run

# Test 3: Only check count, skip consolidation
aegis plan YourProject --no-consolidate
```

---

**Summary**: The prompts are now much more explicit, structured, and encourage Claude to think carefully about task clarity. The emphasis has shifted from "complete the request" to "ensure quality and block unclear work."
