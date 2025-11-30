"""High-level Asana service for swarm orchestration."""

import asyncio
from datetime import datetime
from typing import Any

import structlog

from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaSection, AsanaTask, AsanaTaskUpdate

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
        self.custom_field_gids: dict[str, dict[str, str]] = {}  # project_gid -> {name -> gid}
        self.custom_field_enums: dict[str, dict[str, str]] = {}  # field_gid -> {option_name -> option_gid}

    async def ensure_custom_field_gids(self, project_gid: str) -> None:
        """Ensure custom field GIDs are cached for the project.

        Args:
            project_gid: Project GID
        """
        if project_gid in self.custom_field_gids:
            return

        try:
            fields = await self.client.get_project_custom_fields(project_gid)
            self.custom_field_gids[project_gid] = {f["name"]: f["gid"] for f in fields}

            # Cache enum options
            for field in fields:
                if field.get("type") == "enum" and "enum_options" in field:
                    field_gid = field["gid"]
                    self.custom_field_enums[field_gid] = {
                        opt["name"]: opt["gid"]
                        for opt in field["enum_options"]
                    }

            logger.info("custom_fields_cached", project_gid=project_gid, count=len(fields))
        except Exception as e:
            logger.error("custom_field_cache_failed", project_gid=project_gid, error=str(e))
            # Don't raise, just log - we'll try to proceed without custom fields

    async def get_me(self) -> Any:
        """Get the authenticated user.

        Returns:
            AsanaUser object
        """
        return await self.client.get_me()

    async def get_task(self, task_gid: str) -> AsanaTask:
        """Get a task by GID.

        Args:
            task_gid: Task GID

        Returns:
            AsanaTask object
        """
        return await self.client.get_task(task_gid)

    async def get_project(self, project_gid: str) -> Any:
        """Get a project by GID.

        Args:
            project_gid: Project GID

        Returns:
            AsanaProject object
        """
        return await self.client.get_project(project_gid)

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

            if not field_gid:
                raise AsanaServiceError(f"Cannot set custom field: field_gid is None (Task: {task_gid})")

            # Check if this is an enum field and we need to translate the value
            final_value = value
            if field_gid in self.custom_field_enums and isinstance(value, str):
                enum_options = self.custom_field_enums[field_gid]
                if value in enum_options:
                    final_value = enum_options[value]
                    logger.debug(
                        "translated_enum_value",
                        field_gid=field_gid,
                        original_value=value,
                        option_gid=final_value
                    )
                else:
                    logger.warning(
                        "enum_option_not_found",
                        field_gid=field_gid,
                        value=value,
                        available_options=list(enum_options.keys())
                    )

            # Call Asana API to update custom field
            await asyncio.to_thread(
                self.client.tasks_api.update_task,
                {"data": {"custom_fields": {field_gid: final_value}}},
                task_gid,
                {},
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
            Formatted comment text (HTML)
        """
        # Use HTML for rich text in Asana
        comment = f"<body><strong>[{agent_name}]</strong> {status_emoji}<br>"
        comment += f"{summary}<br>"

        if details:
            comment += "<br><strong>Critical Details:</strong><ul>"
            for detail in details:
                comment += f"<li>{detail}</li>"
            comment += "</ul>"

        if session_id:
            comment += f"<br>🔗 <a href='{dashboard_url}/session/{session_id}'>View Session Log</a>"

        comment += "</body>"

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

        await self.client.add_comment(task_gid, comment_text, is_html=True)

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
        assignee: str | None = None,
    ) -> None:
        """Perform a complete task state transition.

        Args:
            task_gid: Task GID
            project_gid: Project GID
            new_section: Target section name
            new_agent: New agent type (updates "Agent" custom field)
            new_status: New status (updates "Swarm Status" custom field)
            clear_session_id: If True, clears "Session ID" custom field
            assignee: User GID or email to assign task to (or "me")

        Raises:
            AsanaServiceError: If transition fails
        """
        logger.info(
            "task_transition_start",
            task_gid=task_gid,
            new_section=new_section,
            new_agent=new_agent,
            new_status=new_status,
            assignee=assignee,
        )

        try:
            # Move to section
            await self.move_task_to_section(task_gid, project_gid, new_section)

            # Update custom fields
            # First, fetch task to get custom field GIDs and enum options
            task = await self.client.get_task(task_gid)

            custom_fields_update = {}

            # Helper to find field and option GIDs
            def find_field_gid(name: str) -> str | None:
                for f in task.custom_fields:
                    if f.get("name") == name:
                        return f.get("gid")
                return None

            def find_enum_option_gid(field_name: str, option_name: str) -> str | None:
                for f in task.custom_fields:
                    if f.get("name") == field_name:
                        for opt in f.get("enum_options", []):
                            if opt.get("name") == option_name:
                                return opt.get("gid")
                return None

            # Prepare updates
            if new_agent:
                field_gid = find_field_gid("Agent")
                option_gid = find_enum_option_gid("Agent", new_agent)
                if field_gid and option_gid:
                    custom_fields_update[field_gid] = option_gid
                else:
                    logger.warning("agent_field_not_found", task_gid=task_gid, agent=new_agent)

            if new_status:
                field_gid = find_field_gid("Swarm Status")
                option_gid = find_enum_option_gid("Swarm Status", new_status)
                if field_gid and option_gid:
                    custom_fields_update[field_gid] = option_gid
                else:
                    logger.warning("status_field_not_found", task_gid=task_gid, status=new_status)

            if clear_session_id:
                field_gid = find_field_gid("Session ID")
                if field_gid:
                    custom_fields_update[field_gid] = ""
                else:
                    logger.warning("session_id_field_not_found", task_gid=task_gid)

            # Prepare task update payload
            from aegis.asana.models import AsanaTaskUpdate
            update_data = AsanaTaskUpdate()

            # Handle assignment
            if assignee:
                if assignee == "me":
                    # Get current user
                    me = await asyncio.to_thread(self.client.users_api.get_user, "me", {})
                    update_data.assignee = me["gid"]
                else:
                    update_data.assignee = assignee

            # Apply updates if any
            if custom_fields_update or update_data.assignee:
                # We need to use the raw API for custom fields mixed with other updates
                # or use update_task for standard fields and a separate call for custom fields?
                # AsanaTaskUpdate doesn't support custom_fields dict directly in the model yet?
                # Let's check AsanaTaskUpdate model. It doesn't have custom_fields.
                # So we should use client.tasks_api.update_task directly for custom fields

                # First apply standard updates (assignee)
                if update_data.assignee:
                    await self.client.update_task(task_gid, update_data)

                # Then apply custom fields
                if custom_fields_update:
                    await asyncio.to_thread(
                        self.client.tasks_api.update_task,
                        {"data": {"custom_fields": custom_fields_update}},
                        task_gid,
                        {},
                    )

                logger.info(
                    "task_fields_updated",
                    task_gid=task_gid,
                    fields=list(custom_fields_update.keys()),
                    assignee=update_data.assignee
                )

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

    async def create_task(
        self,
        project_gid: str,
        name: str,
        notes: str = "",
        section_name: str | None = None,
        agent: str | None = None,
    ) -> AsanaTask:
        """Create a new task in the project.

        Args:
            project_gid: Project GID
            name: Task name
            notes: Task description
            section_name: Optional section to place task in
            agent: Optional agent to assign (sets "Agent" custom field)

        Returns:
            Created AsanaTask
        """
        try:
            # Prepare task data
            data = {
                "name": name,
                "notes": notes,
                "projects": [project_gid],
            }

            # Create task
            task_response = await asyncio.to_thread(
                self.client.tasks_api.create_task,
                {"data": data},
                {"opt_fields": "gid,name,custom_fields"},
            )

            task_dict = task_response if isinstance(task_response, dict) else task_response.to_dict()
            task_gid = task_dict["gid"]

            # Move to section if specified
            if section_name:
                await self.move_task_to_section(task_gid, project_gid, section_name)

            # Set agent if specified
            if agent:
                await self.ensure_custom_field_gids(project_gid)
                field_gid = self.custom_field_gids.get(project_gid, {}).get("Agent")

                # We need to find the enum option GID for this agent
                # This is a bit tricky without full custom field definition
                # For now, let's try to set it if we have the field GID
                # Ideally we should cache enum options too
                pass # TODO: Implement agent field setting on creation

            logger.info("task_created", task_gid=task_gid, name=name)

            # Return full task object
            return await self.client.get_task(task_gid)

        except Exception as e:
            logger.error("task_creation_failed", project_gid=project_gid, name=name, error=str(e))
            raise AsanaServiceError(f"Failed to create task: {e}")
