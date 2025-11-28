"""High-level Asana service for swarm orchestration."""

import asyncio
from datetime import datetime
from typing import Any

import structlog

from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaSection, AsanaTask

logger = structlog.get_logger()


class AsanaServiceError(Exception):
    """Raised when Asana service operations fail."""

    pass


class AsanaService:
    """High-level Asana operations for swarm orchestration.

    Provides:
    - Dependency checking (blocking)
    - Custom field access
    - Section management
    - Task state transitions
    - Comment formatting
    """

    def __init__(self, client: AsanaClient):
        """Initialize Asana service.

        Args:
            client: Configured AsanaClient instance
        """
        self.client = client

    # -------------------------------------------------------------------------
    # Custom Field Helpers
    # -------------------------------------------------------------------------

    def get_custom_field_value(
        self,
        task: AsanaTask,
        field_name: str,
    ) -> Any | None:
        """Get value of a custom field from a task.

        Args:
            task: AsanaTask instance
            field_name: Name of custom field (e.g., "Agent", "Swarm Status")

        Returns:
            Custom field value, or None if not found
        """
        for field in task.custom_fields:
            if field.get("name") == field_name:
                # Handle different field types
                if "enum_value" in field and field["enum_value"]:
                    return field["enum_value"].get("name")
                elif "text_value" in field:
                    return field["text_value"]
                elif "number_value" in field:
                    return field["number_value"]
                elif "display_value" in field:
                    return field["display_value"]
                else:
                    return field.get("value")

        return None

    async def set_custom_field_value(
        self,
        task_gid: str,
        field_gid: str,
        value: str | int | float | None,
    ) -> None:
        """Set value of a custom field on a task.

        Args:
            task_gid: Task GID
            field_gid: Custom field GID
            value: Value to set (format depends on field type)

        Raises:
            AsanaServiceError: If update fails
        """
        try:
            logger.debug(
                "setting_custom_field",
                task_gid=task_gid,
                field_gid=field_gid,
                value=value,
            )

            # Call Asana API to update custom field
            await asyncio.to_thread(
                self.client.tasks_api.update_task,
                task_gid,
                {"data": {"custom_fields": {field_gid: value}}},
            )

            logger.info(
                "custom_field_set",
                task_gid=task_gid,
                field_gid=field_gid,
            )

        except Exception as e:
            logger.error(
                "custom_field_set_failed",
                task_gid=task_gid,
                field_gid=field_gid,
                error=str(e),
            )
            raise AsanaServiceError(f"Failed to set custom field: {e}")

    def get_agent(self, task: AsanaTask) -> str | None:
        """Get agent type from task custom fields.

        Args:
            task: AsanaTask instance

        Returns:
            Agent name (e.g., "Triage", "Worker"), or None if not set
        """
        return self.get_custom_field_value(task, "Agent")

    def get_swarm_status(self, task: AsanaTask) -> str | None:
        """Get swarm status from task custom fields.

        Args:
            task: AsanaTask instance

        Returns:
            Status (e.g., "Idle", "Running"), or None if not set
        """
        return self.get_custom_field_value(task, "Swarm Status")

    def get_session_id(self, task: AsanaTask) -> str | None:
        """Get session ID from task custom fields.

        Args:
            task: AsanaTask instance

        Returns:
            Session ID (UUID), or None if not set
        """
        return self.get_custom_field_value(task, "Session ID")

    def get_cost(self, task: AsanaTask) -> float | None:
        """Get cost from task custom fields.

        Args:
            task: AsanaTask instance

        Returns:
            Cost in USD, or None if not set
        """
        value = self.get_custom_field_value(task, "Cost")
        return float(value) if value is not None else None

    def get_max_cost(self, task: AsanaTask) -> float | None:
        """Get max cost from task custom fields.

        Args:
            task: AsanaTask instance

        Returns:
            Max cost in USD, or None if not set
        """
        value = self.get_custom_field_value(task, "Max Cost")
        return float(value) if value is not None else None

    def get_merge_approval(self, task: AsanaTask) -> str | None:
        """Get merge approval from task custom fields.

        Args:
            task: AsanaTask instance

        Returns:
            Merge approval status, or None if not set
        """
        return self.get_custom_field_value(task, "Merge Approval")

    def get_worktree_path(self, task: AsanaTask) -> str | None:
        """Get worktree path from task custom fields.

        Args:
            task: AsanaTask instance

        Returns:
            Worktree path, or None if not set
        """
        return self.get_custom_field_value(task, "Worktree Path")

    # -------------------------------------------------------------------------
    # Dependency Checking
    # -------------------------------------------------------------------------

    async def get_dependencies(self, task_gid: str) -> list[AsanaTask]:
        """Get tasks that this task depends on.

        Args:
            task_gid: Task GID

        Returns:
            List of dependency tasks
        """
        try:
            logger.debug("fetching_dependencies", task_gid=task_gid)

            # Fetch dependencies from Asana
            response = await asyncio.to_thread(
                self.client.tasks_api.get_dependencies_for_task,
                task_gid,
                {"opt_fields": "name,completed"},
            )

            dependencies = []
            for dep_data in response:
                dep_dict = dep_data if isinstance(dep_data, dict) else dep_data.to_dict()
                # Parse into AsanaTask (simplified, only need gid, name, completed)
                from aegis.asana.models import AsanaTask

                dependencies.append(
                    AsanaTask(
                        gid=dep_dict["gid"],
                        name=dep_dict.get("name", ""),
                        completed=dep_dict.get("completed", False),
                        created_at=datetime.now(),  # Not critical
                        modified_at=datetime.now(),  # Not critical
                    )
                )

            logger.debug(
                "dependencies_fetched",
                task_gid=task_gid,
                count=len(dependencies),
            )

            return dependencies

        except Exception as e:
            logger.error(
                "dependency_fetch_failed",
                task_gid=task_gid,
                error=str(e),
            )
            return []

    async def is_task_blocked(self, task_gid: str) -> bool:
        """Check if task is blocked by incomplete dependencies.

        Args:
            task_gid: Task GID

        Returns:
            True if task has incomplete dependencies (blocked)
        """
        dependencies = await self.get_dependencies(task_gid)

        blocked = any(not dep.completed for dep in dependencies)

        if blocked:
            incomplete_deps = [dep.name for dep in dependencies if not dep.completed]
            logger.info(
                "task_blocked",
                task_gid=task_gid,
                incomplete_dependencies=incomplete_deps,
            )

        return blocked

    # -------------------------------------------------------------------------
    # Section Operations
    # -------------------------------------------------------------------------

    async def get_task_section(
        self,
        task_gid: str,
        project_gid: str,
    ) -> AsanaSection | None:
        """Get section that a task belongs to in a project.

        Args:
            task_gid: Task GID
            project_gid: Project GID

        Returns:
            AsanaSection, or None if task has no section
        """
        try:
            # Get all sections for the project
            sections = await self.client.get_sections(project_gid)

            # Get tasks in each section to find which one contains our task
            for section in sections:
                tasks_in_section = await asyncio.to_thread(
                    self.client.tasks_api.get_tasks_for_section,
                    section.gid,
                    {"opt_fields": "gid"},
                )

                for section_task in tasks_in_section:
                    task_dict = (
                        section_task if isinstance(section_task, dict) else section_task.to_dict()
                    )
                    if task_dict["gid"] == task_gid:
                        return section

            return None

        except Exception as e:
            logger.error(
                "section_lookup_failed",
                task_gid=task_gid,
                project_gid=project_gid,
                error=str(e),
            )
            return None

    async def move_task_to_section(
        self,
        task_gid: str,
        project_gid: str,
        section_name: str,
    ) -> None:
        """Move task to a specific section in a project.

        Args:
            task_gid: Task GID
            project_gid: Project GID
            section_name: Name of target section

        Raises:
            AsanaServiceError: If section not found or move fails
        """
        try:
            # Find section by name
            sections = await self.client.get_sections(project_gid)
            target_section = None

            for section in sections:
                if section.name == section_name:
                    target_section = section
                    break

            if not target_section:
                raise AsanaServiceError(f"Section '{section_name}' not found in project")

            # Move task to section
            await self.client.move_task_to_section(
                task_gid=task_gid,
                project_gid=project_gid,
                section_gid=target_section.gid,
            )

            logger.info(
                "task_moved_to_section",
                task_gid=task_gid,
                section_name=section_name,
            )

        except Exception as e:
            logger.error(
                "task_move_failed",
                task_gid=task_gid,
                section_name=section_name,
                error=str(e),
            )
            raise AsanaServiceError(f"Failed to move task to section: {e}")

    # -------------------------------------------------------------------------
    # Comment Formatting (Per Design Doc)
    # -------------------------------------------------------------------------

    def format_agent_comment(
        self,
        agent_name: str,
        status_emoji: str,
        summary: str,
        details: list[str] | None = None,
        session_id: str | None = None,
        dashboard_url: str = "http://localhost:8501",
    ) -> str:
        """Format agent comment per design doc template.

        Template:
        **[Agent Name]** {Status_Emoji}
        {Concise Summary}

        **Critical Details:**
        * {Detail 1}
        * {Detail 2}

        🔗 [View Session Log](dashboard_url/session/{session_id})

        Args:
            agent_name: Name of agent (e.g., "Triage Agent", "Worker Agent")
            status_emoji: Status emoji (e.g., "✅", "❌", "⚠️", "🔄")
            summary: Concise summary (under 50 words)
            details: List of critical details
            session_id: Session ID for log linking
            dashboard_url: Base URL for dashboard

        Returns:
            Formatted comment text
        """
        comment = f"**[{agent_name}]** {status_emoji}\n{summary}\n"

        if details:
            comment += "\n**Critical Details:**\n"
            for detail in details:
                comment += f"* {detail}\n"

        if session_id:
            comment += f"\n🔗 [View Session Log]({dashboard_url}/session/{session_id})"

        return comment

    async def post_agent_comment(
        self,
        task_gid: str,
        agent_name: str,
        status_emoji: str,
        summary: str,
        details: list[str] | None = None,
        session_id: str | None = None,
    ) -> None:
        """Post formatted agent comment to task.

        Args:
            task_gid: Task GID
            agent_name: Name of agent
            status_emoji: Status emoji
            summary: Concise summary
            details: List of critical details
            session_id: Session ID for log linking
        """
        comment_text = self.format_agent_comment(
            agent_name=agent_name,
            status_emoji=status_emoji,
            summary=summary,
            details=details,
            session_id=session_id,
        )

        await self.client.add_comment(task_gid, comment_text)

        logger.info(
            "agent_comment_posted",
            task_gid=task_gid,
            agent_name=agent_name,
        )

    # -------------------------------------------------------------------------
    # Task State Transitions
    # -------------------------------------------------------------------------

    async def transition_task(
        self,
        task_gid: str,
        project_gid: str,
        new_section: str,
        new_agent: str | None = None,
        new_status: str | None = None,
        clear_session_id: bool = False,
    ) -> None:
        """Perform a complete task state transition.

        Args:
            task_gid: Task GID
            project_gid: Project GID
            new_section: Target section name
            new_agent: New agent type (updates "Agent" custom field)
            new_status: New status (updates "Swarm Status" custom field)
            clear_session_id: If True, clears "Session ID" custom field

        Raises:
            AsanaServiceError: If transition fails
        """
        logger.info(
            "task_transition_start",
            task_gid=task_gid,
            new_section=new_section,
            new_agent=new_agent,
            new_status=new_status,
        )

        try:
            # Move to section
            await self.move_task_to_section(task_gid, project_gid, new_section)

            # Update custom fields if needed
            # Note: This requires custom field GIDs which should be cached
            # For now, we'll log that this needs to be implemented with GID lookup

            logger.warning(
                "custom_field_update_skipped",
                reason="Need to implement GID lookup for custom fields",
                task_gid=task_gid,
            )

            # TODO: Implement custom field GID lookup and update
            # if new_agent:
            #     await self.set_custom_field_value(task_gid, agent_field_gid, new_agent)
            # if new_status:
            #     await self.set_custom_field_value(task_gid, status_field_gid, new_status)
            # if clear_session_id:
            #     await self.set_custom_field_value(task_gid, session_field_gid, "")

            logger.info(
                "task_transition_complete",
                task_gid=task_gid,
                new_section=new_section,
            )

        except Exception as e:
            logger.error(
                "task_transition_failed",
                task_gid=task_gid,
                error=str(e),
            )
            raise AsanaServiceError(f"Task transition failed: {e}")
