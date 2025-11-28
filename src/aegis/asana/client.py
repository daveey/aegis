"""Asana API client wrapper."""

import asyncio
from typing import Any

import asana
import structlog
from asana.rest import ApiException
from tenacity import retry, stop_after_attempt, wait_exponential

from aegis.asana.models import (
    AsanaComment,
    AsanaProject,
    AsanaSection,
    AsanaTask,
    AsanaTaskUpdate,
    AsanaUser,
)

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
        self.sections_api = asana.SectionsApi(self.api_client)
        self.users_api = asana.UsersApi(self.api_client)
        self.portfolios_api = asana.PortfoliosApi(self.api_client)

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
                {"opt_fields": ",".join(opt_fields)},
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
                self.tasks_api.get_task, task_gid, {"opt_fields": ",".join(opt_fields)}
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
                self.tasks_api.update_task, {"data": update_data}, task_gid, {}
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
                {"opt_fields": ",".join(opt_fields)},
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
                {"opt_fields": ",".join(opt_fields)},
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
                self.projects_api.get_project, project_gid, {"opt_fields": ",".join(opt_fields)}
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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get_sections(self, project_gid: str) -> list[AsanaSection]:
        """Get all sections in a project.

        Args:
            project_gid: The GID of the project

        Returns:
            List of AsanaSection objects
        """
        try:
            sections_response = await asyncio.to_thread(
                self.sections_api.get_sections_for_project,
                project_gid,
                {"opt_fields": "name,gid,project.name"},
            )

            sections = []
            for section_data in sections_response:
                section_dict = section_data if isinstance(section_data, dict) else section_data.to_dict()
                sections.append(
                    AsanaSection(
                        gid=section_dict["gid"],
                        name=section_dict["name"],
                        project=section_dict.get("project"),
                    )
                )

            logger.info("fetched_sections", project_gid=project_gid, section_count=len(sections))
            return sections

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), project_gid=project_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def create_section(self, project_gid: str, section_name: str) -> AsanaSection:
        """Create a new section in a project.

        Args:
            project_gid: The GID of the project
            section_name: Name of the section to create

        Returns:
            Created AsanaSection object
        """
        try:
            section_response = await asyncio.to_thread(
                self.sections_api.create_section_for_project,
                project_gid,
                {"body": {"data": {"name": section_name}}, "opt_fields": "name,gid"},
            )

            section_dict = section_response if isinstance(section_response, dict) else section_response.to_dict()
            section = AsanaSection(
                gid=section_dict["gid"],
                name=section_dict["name"],
            )

            logger.info("created_section", project_gid=project_gid, section_name=section_name)
            return section

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), project_gid=project_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def move_task_to_section(self, task_gid: str, project_gid: str, section_gid: str) -> None:
        """Move a task to a specific section within a project.

        Args:
            task_gid: The GID of the task
            project_gid: The GID of the project
            section_gid: The GID of the section
        """
        try:
            await asyncio.to_thread(
                self.sections_api.add_task_for_section,
                section_gid,
                {"body": {"data": {"task": task_gid}}},
            )

            logger.info(
                "moved_task_to_section",
                task_gid=task_gid,
                project_gid=project_gid,
                section_gid=section_gid,
            )

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), task_gid=task_gid)
            raise

    async def ensure_project_sections(
        self, project_gid: str, section_names: list[str]
    ) -> dict[str, str]:
        """Ensure a project has the specified sections, creating them if needed.

        Args:
            project_gid: The GID of the project
            section_names: List of section names that should exist

        Returns:
            Dict mapping section names to section GIDs
        """
        # Get existing sections
        existing_sections = await self.get_sections(project_gid)
        existing_section_map = {s.name: s.gid for s in existing_sections}

        # Create missing sections
        section_map = {}
        for section_name in section_names:
            if section_name in existing_section_map:
                section_map[section_name] = existing_section_map[section_name]
            else:
                new_section = await self.create_section(project_gid, section_name)
                section_map[section_name] = new_section.gid
                logger.info("created_missing_section", project_gid=project_gid, section_name=section_name)

        return section_map

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get_tasks_for_section(self, section_gid: str) -> list[AsanaTask]:
        """Get all tasks in a specific section.

        Args:
            section_gid: The GID of the section

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

            tasks_response = await asyncio.to_thread(
                self.tasks_api.get_tasks_for_section,
                section_gid,
                {"opt_fields": ",".join(opt_fields)},
            )

            tasks = []
            for task_data in tasks_response:
                task_dict = task_data if isinstance(task_data, dict) else task_data.to_dict()
                tasks.append(self._parse_task(task_dict))

            logger.info(
                "fetched_tasks_for_section",
                section_gid=section_gid,
                task_count=len(tasks),
            )
            return tasks

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), section_gid=section_gid)
            raise

    async def complete_task_and_move_to_implemented(
        self, task_gid: str, project_gid: str
    ) -> AsanaTask:
        """Mark a task as complete and move it to the 'Implemented' section.

        Args:
            task_gid: The GID of the task
            project_gid: The GID of the project

        Returns:
            Updated AsanaTask object
        """
        # Mark task as complete
        from aegis.asana.models import AsanaTaskUpdate
        updated_task = await self.update_task(task_gid, AsanaTaskUpdate(completed=True))

        # Get sections and find "Implemented"
        sections = await self.get_sections(project_gid)
        section_map = {s.name: s.gid for s in sections}

        if "Implemented" in section_map:
            # Move to Implemented section
            await self.move_task_to_section(
                task_gid=task_gid,
                project_gid=project_gid,
                section_gid=section_map["Implemented"]
            )
            logger.info("completed_and_moved_task", task_gid=task_gid, section="Implemented")
        else:
            logger.warning("implemented_section_not_found", project_gid=project_gid)

        return updated_task

    async def complete_task_and_move_to_answered(
        self, task_gid: str, project_gid: str
    ) -> AsanaTask:
        """Mark a task as complete and move it to the 'Answered' section.

        This is used for question tasks that have been answered.

        Args:
            task_gid: The GID of the task
            project_gid: The GID of the project

        Returns:
            Updated AsanaTask object
        """
        # Mark task as complete
        from aegis.asana.models import AsanaTaskUpdate
        updated_task = await self.update_task(task_gid, AsanaTaskUpdate(completed=True))

        # Get sections and find "Answered"
        sections = await self.get_sections(project_gid)
        section_map = {s.name: s.gid for s in sections}

        if "Answered" in section_map:
            # Move to Answered section
            await self.move_task_to_section(
                task_gid=task_gid,
                project_gid=project_gid,
                section_gid=section_map["Answered"]
            )
            logger.info("completed_and_moved_task", task_gid=task_gid, section="Answered")
        else:
            logger.warning("answered_section_not_found", project_gid=project_gid)

        return updated_task

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def create_task(
        self,
        project_gid: str,
        name: str,
        notes: str | None = None,
        assignee: str | None = None,
    ) -> AsanaTask:
        """Create a new task in a project.

        Args:
            project_gid: The GID of the project
            name: Task name
            notes: Task description/notes
            assignee: User GID to assign the task to

        Returns:
            Created AsanaTask object
        """
        try:
            task_data = {
                "name": name,
                "projects": [project_gid],
            }
            if notes:
                task_data["notes"] = notes
            if assignee:
                task_data["assignee"] = assignee

            task_response = await asyncio.to_thread(
                self.tasks_api.create_task,
                {"data": task_data},
                {"opt_fields": "name,gid,notes,permalink_url"},
            )

            task_dict = task_response if isinstance(task_response, dict) else task_response.to_dict()
            logger.info("created_task", project_gid=project_gid, task_name=name)
            return self._parse_task(task_dict)

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), project_gid=project_gid)
            raise

    async def get_current_user(self) -> AsanaUser:
        """Get the current authenticated user.

        Returns:
            AsanaUser object for the authenticated user
        """
        try:
            user_response = await asyncio.to_thread(
                self.users_api.get_user, "me", {"opt_fields": "name,email,gid"}
            )

            user_dict = user_response if isinstance(user_response, dict) else user_response.to_dict()
            user = AsanaUser(
                gid=user_dict["gid"],
                name=user_dict["name"],
                email=user_dict.get("email"),
            )

            logger.info("fetched_current_user", user_name=user.name, user_gid=user.gid)
            return user

        except ApiException as e:
            logger.error("asana_api_error", error=str(e))
            raise

    def extract_mentions_from_text(self, text: str) -> list[str]:
        """Extract @mentions from text.

        Asana mentions in API responses appear as:
        - In plain text: @username
        - In HTML: <a data-asana-gid="USER_GID">@username</a>

        Args:
            text: Text content (can be plain or HTML)

        Returns:
            List of mentioned user names (without @ prefix)
        """
        import re

        mentions = []

        # Pattern 1: HTML format with data-asana-gid
        html_pattern = r'<a[^>]*data-asana-gid="(\d+)"[^>]*>@([^<]+)</a>'
        html_matches = re.findall(html_pattern, text)
        for _gid, name in html_matches:
            mentions.append(name.strip())

        # Pattern 2: Plain @ mentions (fallback)
        # Only match if not already captured in HTML
        if not html_matches:
            plain_pattern = r'@(\w+(?:\s+\w+)*)'
            plain_matches = re.findall(plain_pattern, text)
            mentions.extend([m.strip() for m in plain_matches])

        logger.debug("extracted_mentions", text_length=len(text), mention_count=len(mentions))
        return mentions

    async def get_teammates_from_project(self, project_gid: str) -> dict[str, AsanaTask]:
        """Get all team-mate tasks from a Team project.

        Args:
            project_gid: The GID of the Team project

        Returns:
            Dictionary mapping team-mate names to their task objects
        """
        tasks = await self.get_tasks_from_project(project_gid, assigned_only=False)
        teammates = {}

        for task in tasks:
            # Each task represents a team-mate
            # Task name is the team-mate's name
            # Task notes contain the team-mate's prompt
            if task.name and not task.completed:
                teammates[task.name] = task
                logger.debug("found_teammate", name=task.name, task_gid=task.gid)

        logger.info("fetched_teammates", project_gid=project_gid, teammate_count=len(teammates))
        return teammates

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def create_project(
        self,
        workspace_gid: str,
        name: str,
        notes: str | None = None,
        public: bool = True,
        team_gid: str | None = None,
    ) -> AsanaProject:
        """Create a new project in a workspace.

        Args:
            workspace_gid: The GID of the workspace
            name: Project name
            notes: Project description/notes
            public: Whether the project is public to the workspace
            team_gid: The GID of the team (required for organizations)

        Returns:
            Created AsanaProject object
        """
        try:
            project_data = {
                "name": name,
            }
            if notes:
                project_data["notes"] = notes
            if team_gid:
                project_data["team"] = team_gid

            project_response = await asyncio.to_thread(
                self.projects_api.create_project_for_workspace,
                {"data": project_data},
                workspace_gid,
                {"opt_fields": "name,gid,notes,archived,public"},
            )

            project_dict = project_response if isinstance(project_response, dict) else project_response.to_dict()
            project = AsanaProject(
                gid=project_dict["gid"],
                name=project_dict["name"],
                notes=project_dict.get("notes"),
                archived=project_dict.get("archived", False),
                public=project_dict.get("public", False),
            )

            logger.info("created_project", workspace_gid=workspace_gid, project_name=name, project_gid=project.gid)
            return project

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), workspace_gid=workspace_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def add_project_to_portfolio(self, portfolio_gid: str, project_gid: str) -> None:
        """Add a project to a portfolio.

        Args:
            portfolio_gid: The GID of the portfolio
            project_gid: The GID of the project to add
        """
        try:
            await asyncio.to_thread(
                self.portfolios_api.add_item_for_portfolio,
                {"data": {"item": project_gid}},
                portfolio_gid,
            )

            logger.info(
                "added_project_to_portfolio",
                portfolio_gid=portfolio_gid,
                project_gid=project_gid,
            )

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), portfolio_gid=portfolio_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def add_reaction_to_story(self, story_gid: str, emoji: str = "thumbs_up") -> None:
        """Add a reaction/emoji to a story (comment).

        Args:
            story_gid: The GID of the story/comment
            emoji: The emoji to add (default: thumbs_up)
        """
        try:
            # Use the stories API to add a reaction
            await asyncio.to_thread(
                self.stories_api.create_story_for_task,
                {"data": {"resource_type": "like"}},
                story_gid,
                {},
            )

            logger.info("added_reaction_to_story", story_gid=story_gid, emoji=emoji)

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), story_gid=story_gid)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def get_projects_from_portfolio(self, portfolio_gid: str) -> list[AsanaProject]:
        """Get all projects from a portfolio.

        Args:
            portfolio_gid: The GID of the portfolio

        Returns:
            List of AsanaProject objects
        """
        try:
            opt_fields = ["name", "notes", "archived", "public", "permalink_url", "team.name", "workspace.name"]

            projects_response = await asyncio.to_thread(
                self.portfolios_api.get_items_for_portfolio,
                portfolio_gid,
                {"opt_fields": ",".join(opt_fields)},
            )

            projects = []
            for project_data in projects_response:
                project_dict = project_data if isinstance(project_data, dict) else project_data.to_dict()
                projects.append(
                    AsanaProject(
                        gid=project_dict["gid"],
                        name=project_dict["name"],
                        notes=project_dict.get("notes"),
                        archived=project_dict.get("archived", False),
                        public=project_dict.get("public", False),
                    )
                )

            logger.info(
                "fetched_projects_from_portfolio",
                portfolio_gid=portfolio_gid,
                project_count=len(projects),
            )
            return projects

        except ApiException as e:
            logger.error("asana_api_error", error=str(e), portfolio_gid=portfolio_gid)
            raise
