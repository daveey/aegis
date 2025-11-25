# Autonomous Work Pattern

## Overview

The `aegis work-on [project]` command implements an autonomous agent pattern that can:
1. Assess the current state of a project
2. Identify blockers and ask questions to the user
3. Execute ready tasks without manual intervention
4. Work through multiple tasks in a single session

This is a more intelligent evolution of the simple `aegis do [project]` command.

## Command Comparison

### `aegis do [project]` (Simple Executor)
- Picks the **first** incomplete task
- Executes it immediately without assessment
- Single task execution
- No dependency awareness
- No question handling

### `aegis work-on [project]` (Autonomous Agent)
- Analyzes **all** incomplete unassigned tasks
- Assesses project state and dependencies
- Identifies blockers and creates question tasks
- Works on multiple ready tasks
- Intelligent task selection

## Work-On Algorithm

```
1. ASSESS PROJECT STATE
   └─ Fetch all incomplete unassigned tasks
   └─ Analyze task descriptions for dependencies
   └─ Identify current project state (e.g., "Database Setup" phase)

2. IDENTIFY BLOCKERS
   └─ Check for missing prerequisites
   └─ Check for unclear requirements
   └─ Check for environment setup needs

3. ASK QUESTIONS
   └─ Create question tasks in Asana
   └─ Assign to user (David)
   └─ Block on these questions if critical

4. SELECT READY TASKS
   └─ Filter out blocked tasks
   └─ Prioritize by:
      - Dependencies (foundational tasks first)
      - Explicit order in task list
      - Criticality for project progress

5. EXECUTE READY TASKS
   └─ Work through tasks sequentially
   └─ Log all work to project log file
   └─ Update Asana with results
   └─ Continue until:
      - All ready tasks complete, OR
      - Hit a blocker, OR
      - Timeout/max tasks reached

6. SUMMARIZE SESSION
   └─ Report what was completed
   └─ Report what's blocked
   └─ Report questions asked
   └─ Suggest next steps
```

## Example Session

```bash
$ aegis work-on aegis

Analyzing Aegis project...
✓ Found 17 incomplete tasks

Assessing project state...
• Current phase: Database Setup (Phase 1)
• Next phase: Agent Framework (Phase 2)

Checking for blockers...
⚠ Blocker found: PostgreSQL not set up
  Question created: "PostgreSQL setup preference?" (assigned to David)

Selecting ready tasks...
✓ Ready: Create database CRUD operations (blocked by DB)
✓ Ready: Design base Agent class (no dependencies)
✓ Ready: Implement Anthropic API client wrapper (no dependencies)

Executing ready tasks (2 tasks)...

[1/2] Design base Agent class
  Working directory: /Users/daveey/code/aegis
  ✓ Created: src/aegis/agents/base.py
  ✓ Updated: tests/unit/test_agent_base.py
  ✓ Asana updated

[2/2] Implement Anthropic API client wrapper
  Working directory: /Users/daveey/code/aegis
  ✓ Created: src/aegis/agents/llm_client.py
  ✓ Updated: tests/unit/test_llm_client.py
  ✓ Asana updated

Session Summary:
  ✓ Completed: 2 tasks
  ⚠ Blocked: 5 tasks (waiting on PostgreSQL)
  ? Questions: 1 question (assigned to David)

Next steps:
  1. Answer question "PostgreSQL setup preference?"
  2. Run `aegis work-on aegis` again to continue

Log: /Users/daveey/code/aegis/logs/aegis.log
```

## Implementation Design

### Core Components

#### 1. Project State Analyzer
```python
class ProjectStateAnalyzer:
    def analyze(self, project_gid: str) -> ProjectState:
        """Analyze current state of project."""
        # Fetch all tasks
        # Identify current phase
        # Detect dependencies between tasks
        # Return structured state
```

#### 2. Blocker Detector
```python
class BlockerDetector:
    def find_blockers(self, tasks: list[Task]) -> list[Blocker]:
        """Find blockers across tasks."""
        # Check for missing dependencies
        # Check for unclear requirements
        # Check for environment issues
        # Return list of blockers with questions
```

#### 3. Question Creator
```python
class QuestionCreator:
    async def create_question(
        self,
        project_gid: str,
        assignee_gid: str,
        question: Question
    ) -> Task:
        """Create question task in Asana."""
        # Format question nicely
        # Add context from current work
        # Assign to user
        # Return task GID
```

#### 4. Task Selector
```python
class TaskSelector:
    def select_ready_tasks(
        self,
        tasks: list[Task],
        blockers: list[Blocker]
    ) -> list[Task]:
        """Select tasks that are ready to execute."""
        # Filter out blocked tasks
        # Sort by priority/dependencies
        # Return ordered list
```

#### 5. Autonomous Executor
```python
class AutonomousExecutor:
    async def work_on_project(self, project_name: str):
        """Main entry point for work-on command."""
        # 1. Analyze project state
        # 2. Detect blockers
        # 3. Create questions if needed
        # 4. Select ready tasks
        # 5. Execute tasks sequentially
        # 6. Summarize session
```

## Configuration

```python
# In .env or config
AEGIS_MAX_TASKS_PER_SESSION=5  # Max tasks to execute in one work-on session
AEGIS_AUTO_ASSIGN_QUESTIONS=true  # Auto-assign questions to portfolio owner
AEGIS_WORK_MODE=sequential  # sequential | parallel
```

## CLI Interface

```bash
# Basic usage
aegis work-on [project]

# Options
aegis work-on [project] --max-tasks 3       # Limit tasks per session
aegis work-on [project] --no-questions      # Don't create question tasks
aegis work-on [project] --dry-run           # Show what would be done
aegis work-on [project] --phase "Phase 2"   # Focus on specific phase
```

## Question Task Format

When creating questions, use this format:

```markdown
**From**: Claude (Aegis Autonomous Agent)
**Context**: Working on task "[Task Name]"
**Blocker**: [Brief description]

## Question

[Clear, specific question]

## Options

1. **Option A** - [Description]
   - Pros: ...
   - Cons: ...

2. **Option B** - [Description]
   - Pros: ...
   - Cons: ...

## Recommendation

[Claude's recommendation with reasoning]

## Action Needed

[What user should do - e.g., "Reply in comments with your choice"]
```

## Task Dependency Detection

Tasks can indicate dependencies in their descriptions:

```markdown
**Dependencies**: Requires PostgreSQL running

**Depends on**:
- Task: "Set up PostgreSQL database"
- Task: "Configure Alembic migrations"

**Blocked by**: Need to decide on authentication strategy
```

The analyzer should parse these patterns to build dependency graph.

## Benefits

1. **More Autonomous**: Can work through multiple tasks without intervention
2. **Intelligent**: Understands dependencies and blockers
3. **Communicative**: Asks questions when needed instead of getting stuck
4. **Efficient**: Maximizes work done per session
5. **Transparent**: Clear reporting of what was done and what's blocked

## Future Enhancements

1. **Parallel Execution**: Work on independent tasks concurrently
2. **Learning**: Remember user preferences for similar questions
3. **Smart Retries**: Retry tasks that failed due to transient issues
4. **Progress Tracking**: Visual progress bar for long sessions
5. **Cost Estimation**: Estimate cost/time before starting
6. **Undo Support**: Roll back changes if something goes wrong

## Comparison to Full Orchestrator

The `work-on` command is a manual/on-demand version of what the full orchestrator will do:

- **work-on**: User triggers, single project, one session
- **Orchestrator**: Continuous, all projects, ongoing

The orchestrator (Phase 3) will essentially run `work-on` logic continuously across all projects in the portfolio.

## Testing Strategy

1. **Unit Tests**: Test each component in isolation
2. **Integration Tests**: Test full work-on flow with mock Asana
3. **Real World Tests**: Test on actual Aegis project
4. **Edge Cases**:
   - All tasks blocked
   - No tasks available
   - Questions timeout
   - Circular dependencies

## Success Metrics

A successful `work-on` session should:
- Complete at least 1 task (if any are ready)
- Create clear questions for blockers
- Not repeat work or create duplicates
- Leave project in a valid state
- Generate clear, actionable summary
