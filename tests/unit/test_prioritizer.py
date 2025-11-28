"""Tests for task prioritization engine."""

from datetime import UTC, datetime, timedelta

import pytest

from aegis.asana.models import AsanaProject, AsanaTask
from aegis.orchestrator.prioritizer import (
    PriorityWeights,
    TaskPrioritizer,
    TaskScore,
)


def create_task(**overrides):
    """Helper to create test tasks with default values."""
    defaults = {
        "gid": "123",
        "name": "Test Task",
        "notes": "Test notes",
        "completed": False,
        "created_at": datetime.now(UTC),
        "modified_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return AsanaTask(**defaults)


@pytest.fixture
def prioritizer():
    """Create a basic prioritizer with default weights."""
    return TaskPrioritizer()


@pytest.fixture
def prioritizer_custom_weights():
    """Create a prioritizer with custom weights for testing."""
    weights = PriorityWeights(
        due_date=5.0,
        dependency=3.0,
        user_priority=2.0,
        project_importance=1.0,
        age_factor=1.0,
    )
    return TaskPrioritizer(weights=weights)


class TestPriorityWeights:
    """Test PriorityWeights configuration."""

    def test_default_weights(self):
        """Test default weight values."""
        weights = PriorityWeights()
        assert weights.due_date == 10.0
        assert weights.dependency == 8.0
        assert weights.user_priority == 7.0
        assert weights.project_importance == 5.0
        assert weights.age_factor == 3.0

    def test_custom_weights(self):
        """Test custom weight configuration."""
        weights = PriorityWeights(
            due_date=5.0,
            dependency=3.0,
            user_priority=2.0,
            project_importance=1.0,
            age_factor=0.5,
        )
        assert weights.due_date == 5.0
        assert weights.dependency == 3.0
        assert weights.user_priority == 2.0
        assert weights.project_importance == 1.0
        assert weights.age_factor == 0.5


class TestDueDateScoring:
    """Test due date urgency scoring."""

    def test_overdue_task(self, prioritizer):
        """Test scoring for overdue tasks."""
        yesterday = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d")
        task = create_task(due_on=yesterday)

        score = prioritizer._calculate_due_date_score(task)
        assert score == 10.0  # Highest urgency

    def test_due_today(self, prioritizer):
        """Test scoring for tasks due today."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        task = create_task(due_on=today)

        score = prioritizer._calculate_due_date_score(task)
        assert score == 9.0

    def test_due_this_week(self, prioritizer):
        """Test scoring for tasks due within a week."""
        next_week = (datetime.now(UTC) + timedelta(days=5)).strftime("%Y-%m-%d")
        task = create_task(due_on=next_week)

        score = prioritizer._calculate_due_date_score(task)
        assert score == 7.0

    def test_due_this_month(self, prioritizer):
        """Test scoring for tasks due within a month."""
        next_month = (datetime.now(UTC) + timedelta(days=20)).strftime("%Y-%m-%d")
        task = create_task(due_on=next_month)

        score = prioritizer._calculate_due_date_score(task)
        assert score == 5.0

    def test_due_later(self, prioritizer):
        """Test scoring for tasks due far in the future."""
        far_future = (datetime.now(UTC) + timedelta(days=60)).strftime("%Y-%m-%d")
        task = create_task(due_on=far_future)

        score = prioritizer._calculate_due_date_score(task)
        assert score == 3.0

    def test_no_due_date(self, prioritizer):
        """Test scoring for tasks without due dates."""
        task = create_task(due_on=None)

        score = prioritizer._calculate_due_date_score(task)
        assert score == 2.0  # Low priority for tasks without deadlines


class TestDependencyScoring:
    """Test dependency-based scoring."""

    def test_parent_task(self, prioritizer):
        """Test scoring for parent tasks (with subtasks)."""
        task = create_task(num_subtasks=3)

        score = prioritizer._calculate_dependency_score(task)
        assert score == 8.0  # High priority to unblock children

    def test_child_task(self, prioritizer):
        """Test scoring for child tasks (subtasks)."""
        task = create_task(parent={"gid": "456", "name": "Parent Task"})

        score = prioritizer._calculate_dependency_score(task)
        assert score == 3.0  # Lower priority (parent should go first)

    def test_standalone_task(self, prioritizer):
        """Test scoring for standalone tasks."""
        task = create_task(num_subtasks=0, parent=None)

        score = prioritizer._calculate_dependency_score(task)
        assert score == 5.0  # Medium priority


class TestUserPriorityScoring:
    """Test user-assigned priority scoring."""

    def test_high_priority_enum(self, prioritizer):
        """Test high priority from custom field enum."""
        custom_fields = [
            {
                "name": "Priority",
                "enum_value": {"name": "High"},
            }
        ]
        task = create_task(custom_fields=custom_fields)

        score = prioritizer._calculate_user_priority_score(task)
        assert score == 10.0

    def test_medium_priority_enum(self, prioritizer):
        """Test medium priority from custom field enum."""
        custom_fields = [
            {
                "name": "Priority",
                "enum_value": {"name": "Medium"},
            }
        ]
        task = create_task(custom_fields=custom_fields)

        score = prioritizer._calculate_user_priority_score(task)
        assert score == 5.0

    def test_low_priority_enum(self, prioritizer):
        """Test low priority from custom field enum."""
        custom_fields = [
            {
                "name": "Priority",
                "enum_value": {"name": "Low"},
            }
        ]
        task = create_task(custom_fields=custom_fields)

        score = prioritizer._calculate_user_priority_score(task)
        assert score == 2.0

    def test_numeric_priority(self, prioritizer):
        """Test numeric priority field."""
        custom_fields = [
            {
                "name": "Importance",
                "number_value": 8.5,
            }
        ]
        task = create_task(custom_fields=custom_fields)

        score = prioritizer._calculate_user_priority_score(task)
        assert score == 8.5

    def test_no_priority_field(self, prioritizer):
        """Test default priority when no custom field exists."""
        task = create_task(custom_fields=[])

        score = prioritizer._calculate_user_priority_score(task)
        assert score == 5.0  # Default medium priority


class TestProjectScoring:
    """Test project importance scoring."""

    def test_project_with_importance(self):
        """Test scoring for task in important project."""
        project_map = {"proj_123": 9.0}
        prioritizer = TaskPrioritizer(project_importance_map=project_map)

        projects = [AsanaProject(gid="proj_123", name="Important Project")]
        task = create_task(projects=projects)

        score = prioritizer._calculate_project_score(task)
        assert score == 9.0

    def test_multiple_projects(self):
        """Test scoring for task in multiple projects (uses highest)."""
        project_map = {
            "proj_1": 3.0,
            "proj_2": 8.0,
            "proj_3": 5.0,
        }
        prioritizer = TaskPrioritizer(project_importance_map=project_map)

        projects = [
            AsanaProject(gid="proj_1", name="Project 1"),
            AsanaProject(gid="proj_2", name="Project 2"),
            AsanaProject(gid="proj_3", name="Project 3"),
        ]
        task = create_task(projects=projects)

        score = prioritizer._calculate_project_score(task)
        assert score == 8.0  # Highest importance

    def test_project_without_importance(self, prioritizer):
        """Test default scoring for project without importance mapping."""
        projects = [AsanaProject(gid="unknown_proj", name="Unknown Project")]
        task = create_task(projects=projects)

        score = prioritizer._calculate_project_score(task)
        assert score == 5.0  # Default medium importance

    def test_no_project(self, prioritizer):
        """Test scoring for task not in any project."""
        task = create_task(projects=[])

        score = prioritizer._calculate_project_score(task)
        assert score == 5.0


class TestAgeScoring:
    """Test task age scoring (anti-starvation)."""

    def test_very_old_task(self, prioritizer):
        """Test scoring for very old tasks."""
        old_date = datetime.now(UTC) - timedelta(days=70)
        task = create_task(created_at=old_date)

        score = prioritizer._calculate_age_score(task)
        assert score == 8.0  # High priority to prevent starvation

    def test_old_task(self, prioritizer):
        """Test scoring for old tasks."""
        old_date = datetime.now(UTC) - timedelta(days=40)
        task = create_task(created_at=old_date)

        score = prioritizer._calculate_age_score(task)
        assert score == 6.0

    def test_medium_age_task(self, prioritizer):
        """Test scoring for medium age tasks."""
        medium_date = datetime.now(UTC) - timedelta(days=15)
        task = create_task(created_at=medium_date)

        score = prioritizer._calculate_age_score(task)
        assert score == 4.0

    def test_new_task(self, prioritizer):
        """Test scoring for new tasks."""
        recent_date = datetime.now(UTC) - timedelta(days=2)
        task = create_task(created_at=recent_date)

        score = prioritizer._calculate_age_score(task)
        assert score == 2.0


class TestCompletePrioritization:
    """Test complete prioritization workflow."""

    def test_prioritize_empty_list(self, prioritizer):
        """Test prioritizing empty task list."""
        result = prioritizer.prioritize_tasks([])
        assert result == []

    def test_prioritize_single_task(self):
        """Test prioritizing single task."""
        prioritizer = TaskPrioritizer()
        task = create_task()

        result = prioritizer.prioritize_tasks([task])
        assert len(result) == 1
        assert result[0][0] == task
        assert isinstance(result[0][1], TaskScore)

    def test_prioritize_by_due_date(self):
        """Test that overdue tasks are prioritized over future tasks."""
        prioritizer = TaskPrioritizer()

        # Create overdue task
        overdue_task = create_task(
            gid="overdue",
            name="Overdue Task",
            due_on=(datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d"),
        )

        # Create future task
        future_task = create_task(
            gid="future",
            name="Future Task",
            due_on=(datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%d"),
        )

        result = prioritizer.prioritize_tasks([future_task, overdue_task])

        # Overdue task should be first
        assert result[0][0].gid == "overdue"
        assert result[1][0].gid == "future"
        assert result[0][1].total_score > result[1][1].total_score

    def test_prioritize_by_dependencies(self):
        """Test that parent tasks are prioritized over child tasks."""
        prioritizer = TaskPrioritizer()

        # Create parent task
        parent_task = create_task(
            gid="parent",
            name="Parent Task",
            num_subtasks=3,
        )

        # Create child task
        child_task = create_task(
            gid="child",
            name="Child Task",
            parent={"gid": "parent", "name": "Parent Task"},
        )

        result = prioritizer.prioritize_tasks([child_task, parent_task])

        # Parent task should be first
        assert result[0][0].gid == "parent"
        assert result[1][0].gid == "child"

    def test_prioritize_complex_scenario(self):
        """Test prioritization with multiple competing factors."""
        project_map = {"important_proj": 9.0, "normal_proj": 5.0}
        prioritizer = TaskPrioritizer(project_importance_map=project_map)

        # Task 1: Overdue, in normal project
        task1 = create_task(
            gid="task1",
            name="Overdue Normal",
            due_on=(datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d"),
            projects=[AsanaProject(gid="normal_proj", name="Normal")],
        )

        # Task 2: Due next week, parent task, in important project
        task2 = create_task(
            gid="task2",
            name="Important Parent",
            due_on=(datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%d"),
            num_subtasks=2,
            projects=[AsanaProject(gid="important_proj", name="Important")],
        )

        # Task 3: No due date, child task, old
        old_date = datetime.now(UTC) - timedelta(days=45)
        task3 = create_task(
            gid="task3",
            name="Old Child",
            created_at=old_date,
            parent={"gid": "parent", "name": "Parent"},
        )

        result = prioritizer.prioritize_tasks([task3, task1, task2])

        # Verify all tasks are included
        assert len(result) == 3

        # Task 3 (old child) should be lowest priority
        assert result[2][0].gid == "task3"

        # Either task1 or task2 could reasonably be first depending on weights
        # Task1 has high urgency (overdue), Task2 has high project importance + parent status
        top_two_gids = {result[0][0].gid, result[1][0].gid}
        assert top_two_gids == {"task1", "task2"}

        # Scores should be descending
        assert result[0][1].total_score > result[1][1].total_score
        assert result[1][1].total_score > result[2][1].total_score

    def test_get_next_task(self):
        """Test getting the single highest priority task."""
        prioritizer = TaskPrioritizer()

        task1 = create_task(gid="task1", name="Task 1")
        task2 = create_task(
            gid="task2",
            name="Task 2 (Urgent)",
            due_on=(datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d"),
        )

        result = prioritizer.get_next_task([task1, task2])

        assert result is not None
        assert result[0].gid == "task2"  # Overdue task
        assert isinstance(result[1], TaskScore)

    def test_get_next_task_empty(self, prioritizer):
        """Test getting next task from empty list."""
        result = prioritizer.get_next_task([])
        assert result is None


class TestProjectImportanceUpdates:
    """Test dynamic project importance updates."""

    def test_update_project_importance(self, prioritizer):
        """Test updating project importance."""
        prioritizer.update_project_importance("proj_123", 8.5)
        assert prioritizer.project_importance_map["proj_123"] == 8.5

    def test_update_project_importance_invalid(self, prioritizer):
        """Test that invalid importance values are rejected."""
        with pytest.raises(ValueError):
            prioritizer.update_project_importance("proj_123", 11.0)

        with pytest.raises(ValueError):
            prioritizer.update_project_importance("proj_123", -1.0)


class TestTaskScore:
    """Test TaskScore representation."""

    def test_task_score_repr(self):
        """Test string representation of TaskScore."""
        score = TaskScore(
            task_gid="123",
            task_name="Test Task",
            total_score=42.5,
            due_date_score=10.0,
            dependency_score=8.0,
            user_priority_score=7.0,
            project_score=5.0,
            age_score=3.0,
        )

        repr_str = repr(score)
        assert "Test Task" in repr_str
        assert "42.5" in repr_str
        assert "due=10.00" in repr_str

    def test_weighted_score_calculation(self):
        """Test that total score is correctly weighted."""
        weights = PriorityWeights(
            due_date=2.0,
            dependency=1.0,
            user_priority=1.0,
            project_importance=1.0,
            age_factor=1.0,
        )
        prioritizer = TaskPrioritizer(weights=weights)

        # Create task with known scoring characteristics
        task = create_task(
            due_on=(datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%d"),  # Overdue: 10.0
        )

        score = prioritizer._score_task(task)

        # Due date score (10.0) * weight (2.0) = 20.0 (major contributor)
        # Verify that due date is weighted 2x
        assert score.due_date_score == 10.0
        assert score.total_score >= 20.0  # Should have significant weight from due date


class TestAntiStarvation:
    """Test anti-starvation mechanism."""

    def test_old_task_not_starved(self):
        """Test that very old tasks get boosted priority."""
        prioritizer = TaskPrioritizer()

        # Very old task with no due date
        very_old = datetime.now(UTC) - timedelta(days=90)
        old_task = create_task(
            gid="old",
            name="Very Old Task",
            created_at=very_old,
            due_on=None,
        )

        # New task with due date next week
        new_task = create_task(
            gid="new",
            name="New Task",
            due_on=(datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%d"),
        )

        result = prioritizer.prioritize_tasks([old_task, new_task])

        # Both tasks should have reasonable scores
        # Old task should get age boost to compensate for no due date
        old_score = result[0][1] if result[0][0].gid == "old" else result[1][1]
        assert old_score.age_score >= 6.0  # Should have high age score
