"""Task prioritization engine for Aegis orchestrator.

This module implements intelligent task ordering based on multiple factors:
- Due dates (urgency)
- Task dependencies (parent-child relationships)
- User-assigned priority (custom fields)
- Project importance
- Task age (anti-starvation)
"""

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

from aegis.asana.models import AsanaTask

logger = structlog.get_logger()


@dataclass
class PriorityWeights:
    """Configurable weights for different priority factors.

    Each weight represents the relative importance of that factor.
    Default weights are tuned for typical project workflows.
    """

    # Due date urgency (higher for tasks due soon)
    due_date: float = 10.0

    # Task dependencies (parents should be done before children)
    dependency: float = 8.0

    # User-assigned priority from custom fields (if available)
    user_priority: float = 7.0

    # Project importance (can be configured per project)
    project_importance: float = 5.0

    # Task age - prevents starvation of old tasks
    age_factor: float = 3.0


@dataclass
class TaskScore:
    """Detailed scoring breakdown for a task."""

    task_gid: str
    task_name: str
    total_score: float

    # Individual component scores
    due_date_score: float = 0.0
    dependency_score: float = 0.0
    user_priority_score: float = 0.0
    project_score: float = 0.0
    age_score: float = 0.0

    def __repr__(self) -> str:
        """Human-readable score breakdown."""
        return (
            f"TaskScore(task='{self.task_name}', total={self.total_score:.2f}, "
            f"due={self.due_date_score:.2f}, dep={self.dependency_score:.2f}, "
            f"priority={self.user_priority_score:.2f}, project={self.project_score:.2f}, "
            f"age={self.age_score:.2f})"
        )


class TaskPrioritizer:
    """Intelligent task prioritization engine.

    Scores tasks based on multiple factors and returns them in priority order.
    Ensures urgent tasks are handled first while respecting dependencies and
    preventing starvation of older tasks.
    """

    def __init__(
        self,
        weights: PriorityWeights | None = None,
        project_importance_map: dict[str, float] | None = None,
    ) -> None:
        """Initialize the prioritizer.

        Args:
            weights: Custom priority weights (uses defaults if None)
            project_importance_map: Map of project GID to importance score (0-10)
        """
        self.weights = weights or PriorityWeights()
        self.project_importance_map = project_importance_map or {}

        logger.info(
            "initialized_prioritizer",
            weights=self.weights,
            projects_with_importance=len(self.project_importance_map),
        )

    def prioritize_tasks(self, tasks: list[AsanaTask]) -> list[tuple[AsanaTask, TaskScore]]:
        """Sort tasks by priority, returning tasks with their scores.

        Args:
            tasks: List of tasks to prioritize

        Returns:
            List of (task, score) tuples, sorted by priority (highest first)
        """
        if not tasks:
            return []

        # Score all tasks
        scored_tasks = [(task, self._score_task(task)) for task in tasks]

        # Sort by total score (descending)
        sorted_tasks = sorted(scored_tasks, key=lambda x: x[1].total_score, reverse=True)

        logger.info(
            "prioritized_tasks",
            total_tasks=len(tasks),
            top_task=sorted_tasks[0][1].task_name if sorted_tasks else None,
            top_score=sorted_tasks[0][1].total_score if sorted_tasks else 0,
        )

        return sorted_tasks

    def get_next_task(self, tasks: list[AsanaTask]) -> tuple[AsanaTask, TaskScore] | None:
        """Get the highest priority task.

        Args:
            tasks: List of available tasks

        Returns:
            Tuple of (task, score) for highest priority task, or None if no tasks
        """
        prioritized = self.prioritize_tasks(tasks)
        return prioritized[0] if prioritized else None

    def _score_task(self, task: AsanaTask) -> TaskScore:
        """Calculate comprehensive priority score for a task.

        Args:
            task: Task to score

        Returns:
            TaskScore with detailed breakdown
        """
        score = TaskScore(
            task_gid=task.gid,
            task_name=task.name,
            total_score=0.0,
        )

        # 1. Due date urgency score
        score.due_date_score = self._calculate_due_date_score(task)

        # 2. Dependency score (higher for parent tasks)
        score.dependency_score = self._calculate_dependency_score(task)

        # 3. User-assigned priority from custom fields
        score.user_priority_score = self._calculate_user_priority_score(task)

        # 4. Project importance score
        score.project_score = self._calculate_project_score(task)

        # 5. Age score (prevents starvation)
        score.age_score = self._calculate_age_score(task)

        # Calculate weighted total
        score.total_score = (
            score.due_date_score * self.weights.due_date +
            score.dependency_score * self.weights.dependency +
            score.user_priority_score * self.weights.user_priority +
            score.project_score * self.weights.project_importance +
            score.age_score * self.weights.age_factor
        )

        return score

    def _calculate_due_date_score(self, task: AsanaTask) -> float:
        """Calculate urgency score based on due date.

        Scoring:
        - Overdue: 10.0
        - Due today: 9.0
        - Due this week: 7.0
        - Due this month: 5.0
        - Due later: 3.0
        - No due date: 2.0

        Args:
            task: Task to score

        Returns:
            Score from 0-10
        """
        if not task.due_on and not task.due_at:
            return 2.0  # Low priority for tasks without due dates

        # Parse due date
        try:

            if task.due_at:
                due_date = task.due_at
                now = datetime.now(UTC) if due_date.tzinfo else datetime.now()
            elif task.due_on:
                # Parse YYYY-MM-DD format as UTC midnight for consistent comparison
                due_date = datetime.strptime(task.due_on, "%Y-%m-%d").replace(tzinfo=UTC)
                now = datetime.now(UTC)
            else:
                return 2.0

            # For due_on (date only), compare at the date level to handle "today" properly
            if isinstance(due_date, datetime) and not task.due_at:
                # Compare dates only (ignore time)
                today = now.replace(hour=0, minute=0, second=0, microsecond=0)
                due_date_start = due_date.replace(hour=0, minute=0, second=0, microsecond=0)
                days_until_due = (due_date_start - today).days
            else:
                days_until_due = (due_date - now).days

            # Score based on urgency
            if days_until_due < 0:
                return 10.0  # Overdue - highest priority
            elif days_until_due == 0:
                return 9.0  # Due today
            elif days_until_due <= 7:
                return 7.0  # Due this week
            elif days_until_due <= 30:
                return 5.0  # Due this month
            else:
                return 3.0  # Due later

        except (ValueError, TypeError) as e:
            logger.warning("failed_to_parse_due_date", task_gid=task.gid, error=str(e))
            return 2.0

    def _calculate_dependency_score(self, task: AsanaTask) -> float:
        """Calculate score based on task dependencies.

        Parent tasks (tasks with subtasks) should generally be done first
        to unblock their children.

        Scoring:
        - Has subtasks (parent): 8.0
        - Is a subtask (child): 3.0
        - Standalone task: 5.0

        Args:
            task: Task to score

        Returns:
            Score from 0-10
        """
        if task.num_subtasks > 0:
            # Parent task - should be done first to unblock children
            return 8.0
        elif task.parent:
            # Child task - lower priority (parent should be done first)
            return 3.0
        else:
            # Standalone task - medium priority
            return 5.0

    def _calculate_user_priority_score(self, task: AsanaTask) -> float:
        """Calculate score from user-assigned priority custom field.

        Looks for custom fields like:
        - "Priority": High/Medium/Low
        - "Importance": 1-10 scale

        Args:
            task: Task to score

        Returns:
            Score from 0-10
        """
        if not task.custom_fields:
            return 5.0  # Default medium priority

        for field in task.custom_fields:
            field_name = field.get("name", "").lower()

            # Check for "Priority" field
            if "priority" in field_name:
                value = field.get("enum_value")
                if value:
                    value_name = value.get("name", "").lower()
                    if "high" in value_name or "urgent" in value_name:
                        return 10.0
                    elif "medium" in value_name or "normal" in value_name:
                        return 5.0
                    elif "low" in value_name:
                        return 2.0

            # Check for "Importance" or numeric priority field
            if "importance" in field_name or "priority" in field_name:
                number_value = field.get("number_value")
                if number_value is not None:
                    # Assume 0-10 scale, normalize to 0-10
                    return min(10.0, max(0.0, float(number_value)))

        return 5.0  # Default medium priority if no field found

    def _calculate_project_score(self, task: AsanaTask) -> float:
        """Calculate score based on project importance.

        Uses project_importance_map to look up project priority.

        Args:
            task: Task to score

        Returns:
            Score from 0-10
        """
        if not task.projects:
            return 5.0  # Default for tasks not in any project

        # Use the highest importance of all projects the task belongs to
        max_importance = 0.0
        for project in task.projects:
            importance = self.project_importance_map.get(project.gid, 5.0)
            max_importance = max(max_importance, importance)

        return max_importance

    def _calculate_age_score(self, task: AsanaTask) -> float:
        """Calculate score based on task age to prevent starvation.

        Older tasks get slightly higher priority to ensure they're not
        perpetually delayed by newer, urgent tasks.

        Scoring:
        - Very old (>60 days): 8.0
        - Old (30-60 days): 6.0
        - Medium (7-30 days): 4.0
        - New (<7 days): 2.0

        Args:
            task: Task to score

        Returns:
            Score from 0-10
        """
        try:
            now = datetime.now()
            created = task.created_at

            # Make now timezone-aware if created_at is
            if created.tzinfo is not None:
                now = now.replace(tzinfo=UTC)

            age_days = (now - created).days

            if age_days > 60:
                return 8.0  # Very old - don't let it starve
            elif age_days > 30:
                return 6.0  # Old
            elif age_days > 7:
                return 4.0  # Medium age
            else:
                return 2.0  # New task

        except (ValueError, TypeError) as e:
            logger.warning("failed_to_calculate_age", task_gid=task.gid, error=str(e))
            return 4.0  # Default medium score

    def update_project_importance(self, project_gid: str, importance: float) -> None:
        """Update importance score for a specific project.

        Args:
            project_gid: Project GID
            importance: Importance score (0-10)
        """
        if not 0.0 <= importance <= 10.0:
            raise ValueError(f"Importance must be between 0 and 10, got {importance}")

        self.project_importance_map[project_gid] = importance
        logger.info(
            "updated_project_importance",
            project_gid=project_gid,
            importance=importance,
        )
