"""SimpleExecutor agent - processes Asana tasks using Claude API.

This is the first working agent that:
1. Accepts an Asana task as input
2. Generates a prompt from the task description
3. Calls the Claude API
4. Posts the response as an Asana comment
5. Logs execution to the database
"""

import asyncio
import traceback
from datetime import datetime
from typing import Any

import structlog
from anthropic import Anthropic
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
)

from aegis.agents.formatters import TaskStatus, format_error, format_response
from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaTask
from aegis.config import Settings
from aegis.database.models import TaskExecution
from aegis.database.session import get_db_session

logger = structlog.get_logger()


class SimpleExecutor:
    """Simple executor agent that processes tasks using Claude API.

    This agent accepts an Asana task and:
    1. Generates a prompt from the task description
    2. Calls Claude API to process the task
    3. Posts the response as an Asana comment
    4. Logs the execution to the database
    """

    AGENT_TYPE = "simple_executor"
    DEFAULT_MAX_TOKENS = 4096
    DEFAULT_TEMPERATURE = 1.0

    def __init__(
        self,
        config: Settings | None = None,
        asana_client: AsanaClient | None = None,
        anthropic_client: Anthropic | None = None,
    ):
        """Initialize the SimpleExecutor agent.

        Args:
            config: Settings configuration (defaults to Settings())
            asana_client: Asana client instance (optional, will create if not provided)
            anthropic_client: Anthropic client instance (optional, will create if not provided)
        """
        self.config = config or Settings()
        self.asana_client = asana_client or AsanaClient(self.config.asana_access_token)
        self.anthropic_client = anthropic_client or Anthropic(
            api_key=self.config.anthropic_api_key
        )
        logger.info("simple_executor_initialized", agent_type=self.AGENT_TYPE)

    def _generate_prompt(self, task: AsanaTask, project_name: str, code_path: str | None = None) -> str:
        """Generate a prompt for Claude from an Asana task.

        Args:
            task: The Asana task to process
            project_name: Name of the project the task belongs to
            code_path: Optional path to the code repository

        Returns:
            Formatted prompt string for Claude
        """
        prompt_parts = [f"Task: {task.name}"]
        prompt_parts.append(f"\nProject: {project_name}")

        if code_path:
            prompt_parts.append(f"\nCode Location: {code_path}")

        if task.notes:
            prompt_parts.append(f"\n\nTask Description:\n{task.notes}")

        if task.due_on:
            prompt_parts.append(f"\n\nDue Date: {task.due_on}")

        # Add instruction to provide clear, actionable response
        prompt_parts.append(
            "\n\nIMPORTANT: When you have completed this task, "
            "provide a summary of what you accomplished and then EXIT. "
            "Do not wait for further input."
        )

        return "".join(prompt_parts)

    async def _call_claude_api(self, prompt: str) -> tuple[str, dict[str, Any]]:
        """Call the Claude API with the given prompt.

        Args:
            prompt: The prompt to send to Claude

        Returns:
            Tuple of (response_text, metadata) where metadata includes token usage

        Raises:
            Exception: If the API call fails
        """
        logger.info("calling_claude_api", prompt_length=len(prompt))

        try:
            # Call Claude API using the Messages API
            response = await asyncio.to_thread(
                self.anthropic_client.messages.create,
                model=self.config.anthropic_model,
                max_tokens=self.DEFAULT_MAX_TOKENS,
                temperature=self.DEFAULT_TEMPERATURE,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
            )

            # Extract response text
            response_text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    response_text += block.text

            # Extract metadata
            metadata = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "model": response.model,
                "stop_reason": response.stop_reason,
            }

            logger.info(
                "claude_api_success",
                response_length=len(response_text),
                input_tokens=metadata["input_tokens"],
                output_tokens=metadata["output_tokens"],
            )

            return response_text, metadata

        except Exception as e:
            logger.error("claude_api_error", error=str(e), error_type=type(e).__name__)
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _post_response_to_asana(
        self, task_gid: str, response_text: str, status: TaskStatus
    ) -> None:
        """Post the agent's response to Asana as a comment.

        Args:
            task_gid: GID of the task to comment on
            response_text: The response text to post
            status: Status indicator for the response

        Raises:
            Exception: If posting the comment fails after retries
        """
        logger.info("posting_response_to_asana", task_gid=task_gid, status=status)

        try:
            # Format the response
            formatted = format_response(
                response_text, status=status, include_header=True, enhance_markdown=True
            )

            # Post primary comment
            await self.asana_client.add_comment(task_gid, formatted.primary)

            # Post continuation parts if response was split
            if formatted.is_split:
                logger.info(
                    "posting_continuation_parts",
                    task_gid=task_gid,
                    num_parts=len(formatted.continuation_parts),
                )
                for part in formatted.continuation_parts:
                    await self.asana_client.add_comment(task_gid, part)

            logger.info(
                "response_posted_successfully",
                task_gid=task_gid,
                total_length=formatted.total_length,
                is_split=formatted.is_split,
            )

        except Exception as e:
            logger.error(
                "post_response_error",
                task_gid=task_gid,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    def _log_execution(
        self,
        task_gid: str,
        status: str,
        started_at: datetime,
        completed_at: datetime | None = None,
        output: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TaskExecution:
        """Log task execution to the database.

        Args:
            task_gid: GID of the task that was executed
            status: Execution status ('completed', 'failed', 'in_progress', etc.)
            started_at: When execution started
            completed_at: When execution completed (optional)
            output: Output from the execution (optional)
            error_message: Error message if execution failed (optional)
            metadata: Additional metadata (token usage, etc.)

        Returns:
            The created TaskExecution record
        """
        logger.info(
            "logging_execution",
            task_gid=task_gid,
            status=status,
            started_at=started_at,
        )

        # Calculate duration if completed
        duration_seconds = None
        if completed_at:
            duration_seconds = int((completed_at - started_at).total_seconds())

        # Create execution record
        execution = TaskExecution(
            task_id=None,  # We're not linking to Task table yet
            status=status,
            agent_type=self.AGENT_TYPE,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            success=(status == "completed"),
            output=output,
            error_message=error_message,
            input_tokens=metadata.get("input_tokens") if metadata else None,
            output_tokens=metadata.get("output_tokens") if metadata else None,
            execution_metadata=metadata or {},
        )

        with get_db_session() as session:
            session.add(execution)
            session.commit()
            session.refresh(execution)
            # Store ID before session closes to avoid DetachedInstanceError
            execution_id = execution.id
            logger.info("execution_logged", execution_id=execution_id, status=status)
            # Make attributes accessible after session closes
            session.expunge(execution)
            return execution

    async def execute_task(
        self,
        task: AsanaTask,
        project_name: str,
        code_path: str | None = None,
    ) -> dict[str, Any]:
        """Execute an Asana task using Claude API.

        This is the main entry point for the agent. It:
        1. Generates a prompt from the task
        2. Calls Claude API
        3. Posts response to Asana
        4. Logs execution to database

        Args:
            task: The Asana task to execute
            project_name: Name of the project the task belongs to
            code_path: Optional path to the code repository

        Returns:
            Dictionary with execution results including:
            - success: bool
            - output: str (response text)
            - error: str | None
            - execution_id: int
            - metadata: dict (token usage, etc.)
        """
        started_at = datetime.utcnow()
        logger.info(
            "execute_task_started",
            task_gid=task.gid,
            task_name=task.name,
            project_name=project_name,
        )

        try:
            # Generate prompt
            prompt = self._generate_prompt(task, project_name, code_path)
            logger.debug("prompt_generated", prompt_length=len(prompt))

            # Call Claude API
            response_text, api_metadata = await self._call_claude_api(prompt)

            # Post response to Asana
            await self._post_response_to_asana(
                task.gid, response_text, TaskStatus.COMPLETE
            )

            # Log successful execution
            completed_at = datetime.utcnow()
            execution = self._log_execution(
                task_gid=task.gid,
                status="completed",
                started_at=started_at,
                completed_at=completed_at,
                output=response_text,
                metadata=api_metadata,
            )

            logger.info(
                "execute_task_completed",
                task_gid=task.gid,
                execution_id=execution.id,
                duration_seconds=execution.duration_seconds,
            )

            return {
                "success": True,
                "output": response_text,
                "error": None,
                "execution_id": execution.id,
                "metadata": api_metadata,
            }

        except Exception as e:
            # Log error
            error_message = str(e)
            error_traceback = traceback.format_exc()
            completed_at = datetime.utcnow()

            logger.error(
                "execute_task_failed",
                task_gid=task.gid,
                error=error_message,
                error_type=type(e).__name__,
            )

            # Try to post error to Asana
            try:
                error_formatted = format_error(
                    error_message=error_message,
                    error_type=type(e).__name__,
                    traceback=error_traceback,
                    context={"task_gid": task.gid, "project": project_name},
                )
                await self.asana_client.add_comment(task.gid, error_formatted)
            except Exception as post_error:
                logger.error(
                    "failed_to_post_error_to_asana",
                    task_gid=task.gid,
                    error=str(post_error),
                )

            # Log failed execution
            execution = self._log_execution(
                task_gid=task.gid,
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                error_message=error_message,
                metadata={"traceback": error_traceback},
            )

            return {
                "success": False,
                "output": None,
                "error": error_message,
                "execution_id": execution.id,
                "metadata": {"traceback": error_traceback},
            }
