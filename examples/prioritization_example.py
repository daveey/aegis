#!/usr/bin/env python3
"""Example demonstrating task prioritization.

This example shows how to use the Aegis task prioritizer to intelligently
order tasks based on multiple factors.
"""

from datetime import UTC, datetime, timedelta

from aegis.asana.models import AsanaProject, AsanaTask
from aegis.orchestrator.prioritizer import PriorityWeights, TaskPrioritizer


def create_example_tasks() -> list[AsanaTask]:
    """Create a diverse set of example tasks to demonstrate prioritization."""
    now = datetime.now(UTC)

    tasks = [
        # Task 1: Overdue bug fix
        AsanaTask(
            gid="task1",
            name="Fix critical production bug",
            notes="Users cannot log in",
            completed=False,
            created_at=now - timedelta(days=3),
            modified_at=now,
            due_on=(now - timedelta(days=1)).strftime("%Y-%m-%d"),  # Overdue
            projects=[
                AsanaProject(gid="prod_proj", name="Production Support")
            ],
            custom_fields=[
                {"name": "Priority", "enum_value": {"name": "High"}}
            ],
        ),

        # Task 2: New feature in important project
        AsanaTask(
            gid="task2",
            name="Implement new payment integration",
            notes="Add Stripe support",
            completed=False,
            created_at=now - timedelta(days=5),
            modified_at=now,
            due_on=(now + timedelta(days=14)).strftime("%Y-%m-%d"),  # 2 weeks out
            projects=[
                AsanaProject(gid="revenue_proj", name="Revenue Features")
            ],
            num_subtasks=4,  # Parent task with subtasks
        ),

        # Task 3: Old task with no due date
        AsanaTask(
            gid="task3",
            name="Update documentation",
            notes="Refresh API docs",
            completed=False,
            created_at=now - timedelta(days=45),  # Old task
            modified_at=now - timedelta(days=30),
            projects=[
                AsanaProject(gid="docs_proj", name="Documentation")
            ],
        ),

        # Task 4: Subtask (child of task2)
        AsanaTask(
            gid="task4",
            name="Add Stripe API credentials",
            notes="Get credentials from team",
            completed=False,
            created_at=now - timedelta(days=4),
            modified_at=now,
            due_on=(now + timedelta(days=7)).strftime("%Y-%m-%d"),  # 1 week out
            projects=[
                AsanaProject(gid="revenue_proj", name="Revenue Features")
            ],
            parent={"gid": "task2", "name": "Implement new payment integration"},
        ),

        # Task 5: Due today
        AsanaTask(
            gid="task5",
            name="Review pull request #123",
            notes="Security fixes",
            completed=False,
            created_at=now - timedelta(days=1),
            modified_at=now,
            due_on=now.strftime("%Y-%m-%d"),  # Due today
            projects=[
                AsanaProject(gid="dev_proj", name="Development")
            ],
            custom_fields=[
                {"name": "Priority", "enum_value": {"name": "Medium"}}
            ],
        ),

        # Task 6: Low priority, far future
        AsanaTask(
            gid="task6",
            name="Research new frameworks",
            notes="Evaluate Next.js 15",
            completed=False,
            created_at=now - timedelta(days=2),
            modified_at=now,
            due_on=(now + timedelta(days=60)).strftime("%Y-%m-%d"),  # Far future
            projects=[
                AsanaProject(gid="research_proj", name="Research")
            ],
            custom_fields=[
                {"name": "Priority", "enum_value": {"name": "Low"}}
            ],
        ),
    ]

    return tasks


def main():
    """Run the prioritization example."""
    print("=" * 80)
    print("AEGIS TASK PRIORITIZATION EXAMPLE")
    print("=" * 80)
    print()

    # Create example tasks
    tasks = create_example_tasks()
    print(f"Created {len(tasks)} example tasks\n")

    # Define project importance
    project_importance = {
        "prod_proj": 10.0,      # Production - highest importance
        "revenue_proj": 9.0,    # Revenue - very important
        "dev_proj": 6.0,        # Development - important
        "docs_proj": 4.0,       # Documentation - medium
        "research_proj": 3.0,   # Research - lower importance
    }

    # Create prioritizer with default weights
    print("Initializing prioritizer with default weights:")
    weights = PriorityWeights()
    print(f"  - Due date weight: {weights.due_date}")
    print(f"  - Dependency weight: {weights.dependency}")
    print(f"  - User priority weight: {weights.user_priority}")
    print(f"  - Project importance weight: {weights.project_importance}")
    print(f"  - Age factor weight: {weights.age_factor}")
    print()

    prioritizer = TaskPrioritizer(
        weights=weights,
        project_importance_map=project_importance
    )

    # Prioritize tasks
    print("Prioritizing tasks...")
    prioritized = prioritizer.prioritize_tasks(tasks)
    print()

    # Display results
    print("=" * 80)
    print("PRIORITIZED TASK LIST")
    print("=" * 80)
    print()

    for rank, (task, score) in enumerate(prioritized, 1):
        print(f"#{rank} - {task.name}")
        print(f"     GID: {task.gid}")
        print(f"     Total Score: {score.total_score:.2f}")
        print()
        print("     Score Breakdown:")
        print(f"       • Due Date:       {score.due_date_score:.2f} × {weights.due_date:.1f} = {score.due_date_score * weights.due_date:.2f}")
        print(f"       • Dependencies:   {score.dependency_score:.2f} × {weights.dependency:.1f} = {score.dependency_score * weights.dependency:.2f}")
        print(f"       • User Priority:  {score.user_priority_score:.2f} × {weights.user_priority:.1f} = {score.user_priority_score * weights.user_priority:.2f}")
        print(f"       • Project:        {score.project_score:.2f} × {weights.project_importance:.1f} = {score.project_score * weights.project_importance:.2f}")
        print(f"       • Age:            {score.age_score:.2f} × {weights.age_factor:.1f} = {score.age_score * weights.age_factor:.2f}")

        # Add context
        if task.due_on:
            print(f"     Due: {task.due_on}")
        if task.parent:
            print(f"     Subtask of: {task.parent['name']}")
        if task.num_subtasks > 0:
            print(f"     Has {task.num_subtasks} subtasks")

        print()

    # Show what we'd work on next
    print("=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)
    print()

    next_task, next_score = prioritizer.get_next_task(tasks)
    print(f"Next task to work on: {next_task.name}")
    print(f"Priority score: {next_score.total_score:.2f}")
    print()

    # Demonstrate custom weights
    print("=" * 80)
    print("ALTERNATIVE PRIORITIZATION: EMPHASIZE URGENCY")
    print("=" * 80)
    print()

    # Create prioritizer that heavily emphasizes due dates
    urgent_weights = PriorityWeights(
        due_date=20.0,      # Double weight on urgency
        dependency=5.0,
        user_priority=3.0,
        project_importance=2.0,
        age_factor=1.0,
    )

    urgent_prioritizer = TaskPrioritizer(
        weights=urgent_weights,
        project_importance_map=project_importance
    )

    urgent_prioritized = urgent_prioritizer.prioritize_tasks(tasks)

    print("Top 3 tasks with urgency-focused weights:")
    print()
    for rank, (task, score) in enumerate(urgent_prioritized[:3], 1):
        print(f"#{rank} - {task.name}")
        print(f"     Total Score: {score.total_score:.2f}")
        print(f"     Due: {task.due_on or 'No due date'}")
        print()

    print("=" * 80)


if __name__ == "__main__":
    main()
