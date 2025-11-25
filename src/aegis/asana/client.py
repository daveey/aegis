"""Asana API client wrapper."""

import asyncio
from typing import Any

import asana
import structlog
from asana.rest import ApiException
from tenacity import retry, stop_after_attempt, wait_exponential

from aegis.asana.models import AsanaComment, AsanaProject, AsanaTask, AsanaTaskUpdate, AsanaUser

logger = structlog.get_logger()


class AsanaClient:
    """Wrapper around Asana API with async support and rate limiting."""

    def __init__(self, access_token: str) -> None:
        """Initialize Asana client.

        Args:
            access_token: Asana Personal Access Token
        """
        # Configure API client
        configuration = asana.Configuration()
        configuration.access_token = access_token
        self.api_client = asana.ApiClient(configuration)

        # Initialize API instances
        self.tasks_api = asana.TasksApi(self.api_client)
        self.projects_api = asana.ProjectsApi(self.api_client)
        self.stories_api = asana.StoriesApi(self.api_client)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get_tasks_from_project(
        self, project_gid: str, assigned_only: bool = False
    ) -> list[AsanaTask]:
        """Get all tasks from a project.

        Args:
            project_gid: The GID of the project
            assigned_only: If True, only return assigned incomplete tasks

        Returns:
            List of AsanaTask objects
        """
        try:
            opt_fields = [
                "name",
                "notes",
                "html_notes",
                "completed",
                "completed_at",
                "created_at",
                "modified_at",
                "due_on",
                "due_at",
                "assignee.name",
                "assignee.email",
                "assignee_status",
                "projects.name",
                "tags.name",
                "parent.name",
                "num_subtasks",
                "permalink_url",
            ]

            # Run synchronous Asana API call in thread pool
            tasks_response = await asyncio.to_thread(
                self.tasks_api.get_tasks_for_project,
                project_gid,
                opt_fields=",".join(opt_fields),
            )

            tasks = []
            for task_data in tasks_response:
                task_dict = task_data if isinstance(task_data, dict) else task_data.to_dict()
                # Optionally filter for assigned tasks
                if assigned_only and (
                    not task_dict.get("assignee") or task_dict.get("completed")
                ):
                    continue

                tasks.append(self._parse_task(task_dict))

            logger.info(
                "fetched_tasks_from_project",
                project_gid=project_gid,
                task_count=len(tasks),
                assigned_only=assigned_only,
            )
            return tasks

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), project_gid=project_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get_task(self, task_gid: str) -> AsanaTask:
        """Get a single task by GID.

        Args:
            task_gid: The GID of the task

        Returns:
            AsanaTask object
        """
        try:
            opt_fields = [
                "name",
                "notes",
                "html_notes",
                "completed",
                "completed_at",
                "created_at",
                "modified_at",
                "due_on",
                "due_at",
                "assignee.name",
                "assignee.email",
                "assignee_status",
                "projects.name",
                "tags.name",
                "parent.name",
                "num_subtasks",
                "workspace.name",
                "permalink_url",
                "custom_fields",
            ]

            task_response = await asyncio.to_thread(
                self.tasks_api.get_task, task_gid, opt_fields=",".join(opt_fields)
            )

            task_dict = task_response if isinstance(task_response, dict) else task_response.to_dict()
            logger.info("fetched_task", task_gid=task_gid, task_name=task_dict.get("name"))
            return self._parse_task(task_dict)

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), task_gid=task_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def update_task(self, task_gid: str, updates: AsanaTaskUpdate) -> AsanaTask:
        """Update a task.

        Args:
            task_gid: The GID of the task
            updates: AsanaTaskUpdate with fields to update

        Returns:
            Updated AsanaTask object
        """
        try:
            # Build update payload, excluding None values
            update_data = updates.model_dump(exclude_none=True)

            task_response = await asyncio.to_thread(
                self.tasks_api.update_task, {"data": update_data}, task_gid
            )

            task_dict = task_response if isinstance(task_response, dict) else task_response.to_dict()
            logger.info("updated_task", task_gid=task_gid, updates=list(update_data.keys()))
            return self._parse_task(task_dict)

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), task_gid=task_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def add_comment(self, task_gid: str, text: str) -> AsanaComment:
        """Add a comment to a task.

        Args:
            task_gid: The GID of the task
            text: Comment text (supports markdown)

        Returns:
            AsanaComment object
        """
        try:
            opt_fields = ["created_at", "created_by.name", "created_by.email", "text"]

            story_response = await asyncio.to_thread(
                self.stories_api.create_story_for_task,
                {"data": {"text": text}},
                task_gid,
                opt_fields=",".join(opt_fields),
            )

            story_dict = story_response if isinstance(story_response, dict) else story_response.to_dict()
            comment = AsanaComment(
                gid=story_dict["gid"],
                created_at=story_dict["created_at"],
                created_by=AsanaUser(
                    gid=story_dict["created_by"]["gid"],
                    name=story_dict["created_by"]["name"],
                    email=story_dict["created_by"].get("email"),
                ),
                text=story_dict["text"],
            )

            logger.info("added_comment", task_gid=task_gid, comment_length=len(text))
            return comment

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), task_gid=task_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get_comments(self, task_gid: str) -> list[AsanaComment]:
        """Get all comments/stories for a task.

        Args:
            task_gid: The GID of the task

        Returns:
            List of AsanaComment objects
        """
        try:
            opt_fields = ["created_at", "created_by.name", "created_by.email", "text", "type"]

            stories_response = await asyncio.to_thread(
                self.stories_api.get_stories_for_task,
                task_gid,
                opt_fields=",".join(opt_fields),
            )

            comments = []
            for story_obj in stories_response:
                story_dict = story_obj if isinstance(story_obj, dict) else story_obj.to_dict()
                # Only include comment stories, not system stories
                if story_dict.get("type") == "comment" and story_dict.get("text"):
                    comments.append(
                        AsanaComment(
                            gid=story_dict["gid"],
                            created_at=story_dict["created_at"],
                            created_by=AsanaUser(
                                gid=story_dict["created_by"]["gid"],
                                name=story_dict["created_by"]["name"],
                                email=story_dict["created_by"].get("email"),
                            ),
                            text=story_dict["text"],
                        )
                    )

            logger.info("fetched_comments", task_gid=task_gid, comment_count=len(comments))
            return comments

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), task_gid=task_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get_project(self, project_gid: str) -> AsanaProject:
        """Get project details.

        Args:
            project_gid: The GID of the project

        Returns:
            AsanaProject object
        """
        try:
            opt_fields = ["name", "notes", "archived", "public"]

            project_response = await asyncio.to_thread(
                self.projects_api.get_project, project_gid, opt_fields=",".join(opt_fields)
            )

            project_dict = project_response if isinstance(project_response, dict) else project_response.to_dict()
            project = AsanaProject(
                gid=project_dict["gid"],
                name=project_dict["name"],
                notes=project_dict.get("notes"),
                archived=project_dict.get("archived", False),
                public=project_dict.get("public", False),
            )

            logger.info("fetched_project", project_gid=project_gid, project_name=project.name)
            return project

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), project_gid=project_gid)
            raise

    def _parse_task(self, task_data: dict[str, Any]) -> AsanaTask:
        """Parse task data from Asana API into AsanaTask model.

        Args:
            task_data: Raw task data from Asana API

        Returns:
            AsanaTask object
        """
        # Parse assignee if present
        assignee = None
        if task_data.get("assignee"):
            assignee = AsanaUser(
                gid=task_data["assignee"]["gid"],
                name=task_data["assignee"]["name"],
                email=task_data["assignee"].get("email"),
            )

        # Parse projects if present
        projects = []
        if task_data.get("projects"):
            for proj_data in task_data["projects"]:
                projects.append(
                    AsanaProject(
                        gid=proj_data["gid"],
                        name=proj_data["name"],
                    )
                )

        return AsanaTask(
            gid=task_data["gid"],
            name=task_data["name"],
            notes=task_data.get("notes"),
            html_notes=task_data.get("html_notes"),
            completed=task_data.get("completed", False),
            completed_at=task_data.get("completed_at"),
            created_at=task_data["created_at"],
            modified_at=task_data["modified_at"],
            due_on=task_data.get("due_on"),
            due_at=task_data.get("due_at"),
            assignee=assignee,
            assignee_status=task_data.get("assignee_status"),
            projects=projects,
            tags=task_data.get("tags", []),
            parent=task_data.get("parent"),
            num_subtasks=task_data.get("num_subtasks", 0),
            workspace=task_data.get("workspace"),
            permalink_url=task_data.get("permalink_url"),
            custom_fields=task_data.get("custom_fields", []),
        )
