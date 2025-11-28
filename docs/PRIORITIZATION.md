# Task Prioritization

Aegis includes an intelligent task prioritization system that orders tasks based on multiple factors to ensure the most important and urgent work is handled first.

## Overview

The prioritization engine (`src/aegis/orchestrator/prioritizer.py`) scores tasks based on:

1. **Due Dates** (weight: 10.0) - Urgent tasks with approaching or overdue deadlines
2. **Dependencies** (weight: 8.0) - Parent tasks before children to unblock work
3. **User Priority** (weight: 7.0) - Priority set via Asana custom fields
4. **Project Importance** (weight: 5.0) - Tasks in important projects
5. **Task Age** (weight: 3.0) - Anti-starvation for older tasks

## Usage

### Basic Example

```python
from aegis.asana.client import AsanaClient
from aegis.orchestrator.prioritizer import TaskPrioritizer
from aegis.config import get_settings, get_priority_weights_from_settings

# Initialize
settings = get_settings()
client = AsanaClient(settings.asana_access_token)
prioritizer = TaskPrioritizer(weights=get_priority_weights_from_settings())

# Fetch tasks
tasks = await client.get_tasks_from_project(project_gid, assigned_only=True)

# Prioritize tasks
prioritized_tasks = prioritizer.prioritize_tasks(tasks)

# Get highest priority task
for task, score in prioritized_tasks[:3]:
    print(f"{task.name}: {score.total_score:.2f}")
    print(f"  - Due date score: {score.due_date_score:.2f}")
    print(f"  - Dependency score: {score.dependency_score:.2f}")
    print(f"  - User priority score: {score.user_priority_score:.2f}")
    print(f"  - Project score: {score.project_score:.2f}")
    print(f"  - Age score: {score.age_score:.2f}")

# Or just get the next task to work on
next_task, score = prioritizer.get_next_task(tasks)
```

### Custom Weights

You can customize the priority weights in your `.env` file:

```env
# Task Prioritization Weights (higher = more important)
PRIORITY_WEIGHT_DUE_DATE=10.0          # Urgency from due dates
PRIORITY_WEIGHT_DEPENDENCY=8.0          # Parent tasks before children
PRIORITY_WEIGHT_USER_PRIORITY=7.0      # User-assigned priority
PRIORITY_WEIGHT_PROJECT_IMPORTANCE=5.0 # Project-level importance
PRIORITY_WEIGHT_AGE=3.0                # Anti-starvation factor
```

Or programmatically:

```python
from aegis.orchestrator.prioritizer import PriorityWeights, TaskPrioritizer

# Emphasize urgency over everything else
weights = PriorityWeights(
    due_date=20.0,      # Double weight on due dates
    dependency=5.0,
    user_priority=3.0,
    project_importance=2.0,
    age_factor=1.0,
)

prioritizer = TaskPrioritizer(weights=weights)
```

### Project Importance

Set project-level importance to boost all tasks in critical projects:

```python
# Map project GIDs to importance scores (0-10)
project_importance = {
    "critical_project_gid": 10.0,   # Critical project
    "important_project_gid": 7.0,   # Important
    "normal_project_gid": 5.0,      # Normal (default)
}

prioritizer = TaskPrioritizer(project_importance_map=project_importance)

# Update dynamically
prioritizer.update_project_importance("new_project_gid", 8.5)
```

## Scoring Details

### Due Date Scoring

- **Overdue**: 10.0 (highest priority)
- **Due today**: 9.0
- **Due this week**: 7.0
- **Due this month**: 5.0
- **Due later**: 3.0
- **No due date**: 2.0

### Dependency Scoring

- **Parent tasks** (with subtasks): 8.0 - Done first to unblock children
- **Child tasks** (subtasks): 3.0 - Lower priority, wait for parent
- **Standalone tasks**: 5.0 - Medium priority

### User Priority Scoring

Reads from Asana custom fields:

**Priority Field** (enum):
- "High" or "Urgent": 10.0
- "Medium" or "Normal": 5.0
- "Low": 2.0

**Importance Field** (number):
- Uses numeric value directly (0-10 scale)

### Age Scoring (Anti-Starvation)

Prevents old tasks from being perpetually delayed:

- **Very old** (>60 days): 8.0
- **Old** (30-60 days): 6.0
- **Medium** (7-30 days): 4.0
- **New** (<7 days): 2.0

## Integration with Orchestrator

When integrating with the main orchestrator loop:

```python
from aegis.orchestrator.prioritizer import TaskPrioritizer
from aegis.config import get_priority_weights_from_settings

class Orchestrator:
    def __init__(self):
        self.prioritizer = TaskPrioritizer(
            weights=get_priority_weights_from_settings()
        )

    async def process_tasks(self):
        # Fetch all available tasks
        tasks = await self.fetch_available_tasks()

        # Filter out completed tasks
        incomplete_tasks = [t for t in tasks if not t.completed]

        # Prioritize
        prioritized = self.prioritizer.prioritize_tasks(incomplete_tasks)

        # Process in priority order
        for task, score in prioritized[:self.max_concurrent]:
            await self.process_task(task)
```

## Custom Fields Setup in Asana

To enable user priority scoring, create custom fields in your Asana projects:

### Option 1: Priority Enum Field

1. In Asana, go to your project
2. Click "Customize" → "Add Custom Field"
3. Name: "Priority"
4. Type: "Single-select"
5. Options:
   - High
   - Medium
   - Low

### Option 2: Importance Number Field

1. In Asana, go to your project
2. Click "Customize" → "Add Custom Field"
3. Name: "Importance"
4. Type: "Number"
5. Range: 0-10

The prioritizer will automatically detect and use these fields when scoring tasks.

## Testing

Run the comprehensive test suite:

```bash
pytest tests/unit/test_prioritizer.py -v
```

## Performance Considerations

- Scoring is O(n) for n tasks
- Sorting is O(n log n)
- For large task lists (>1000 tasks), consider:
  - Pre-filtering tasks (e.g., assigned only, specific projects)
  - Caching project importance mappings
  - Batching prioritization calls

## Troubleshooting

### Tasks not prioritized as expected

1. Check the weights in your configuration
2. Review the score breakdown for specific tasks
3. Verify custom fields are set up correctly in Asana
4. Check project importance mappings

### Old tasks always appearing first

If age scoring is too high, reduce the `PRIORITY_WEIGHT_AGE` value in your configuration.

### Urgent tasks not prioritized

Increase the `PRIORITY_WEIGHT_DUE_DATE` value to emphasize urgency.
