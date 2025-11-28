"""HTTP client for communicating with agent web services.

This module provides a client for the orchestrator to communicate with
agent processes via their HTTP API.
"""

import asyncio
import re
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


class AgentClient:
    """HTTP client for agent API communication."""

    def __init__(self, host: str, port: int, timeout: float = 30.0):
        """Initialize agent client.

        Args:
            host: Agent host
            port: Agent port
            timeout: Request timeout in seconds
        """
        self.base_url = f"http://{host}:{port}"
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def execute_task(
        self,
        task_gid: str,
        project_name: str,
        code_path: str | None = None
    ) -> dict[str, Any]:
        """Request task execution.

        Args:
            task_gid: Asana task GID
            project_name: Project name
            code_path: Optional code path

        Returns:
            Response dict with keys: task_id, status, message

        Raises:
            httpx.HTTPError: If request fails
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/execute",
                json={
                    "task_gid": task_gid,
                    "project_name": project_name,
                    "code_path": code_path,
                }
            )
            response.raise_for_status()
            data = response.json()

            logger.info(
                "agent_execute_request_sent",
                task_gid=task_gid,
                base_url=self.base_url,
                response=data
            )

            return data

        except httpx.HTTPError as e:
            logger.error(
                "agent_execute_request_failed",
                task_gid=task_gid,
                base_url=self.base_url,
                error=str(e)
            )
            raise

    async def get_status(self, task_id: str) -> dict[str, Any]:
        """Get task status.

        Args:
            task_id: Task ID (Asana GID)

        Returns:
            Status dict with keys: task_id, status, started_at, completed_at,
            success, output, error, log_file

        Raises:
            httpx.HTTPError: If request fails
        """
        try:
            response = await self.client.get(f"{self.base_url}/status/{task_id}")
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error(
                "agent_status_request_failed",
                task_id=task_id,
                base_url=self.base_url,
                error=str(e)
            )
            raise

    async def cancel_task(self, task_id: str) -> dict[str, str]:
        """Cancel a running task.

        Args:
            task_id: Task ID (Asana GID)

        Returns:
            Response dict with keys: status, message

        Raises:
            httpx.HTTPError: If request fails
        """
        try:
            response = await self.client.post(f"{self.base_url}/cancel/{task_id}")
            response.raise_for_status()
            data = response.json()

            logger.info(
                "agent_cancel_request_sent",
                task_id=task_id,
                base_url=self.base_url,
                response=data
            )

            return data

        except httpx.HTTPError as e:
            logger.error(
                "agent_cancel_request_failed",
                task_id=task_id,
                base_url=self.base_url,
                error=str(e)
            )
            raise

    async def health_check(self) -> dict[str, Any]:
        """Check agent health.

        Returns:
            Health dict with keys: status, agent_type, uptime_seconds

        Raises:
            httpx.HTTPError: If request fails
        """
        try:
            response = await self.client.get(f"{self.base_url}/health")
            response.raise_for_status()
            return response.json()

        except httpx.HTTPError as e:
            logger.error(
                "agent_health_check_failed",
                base_url=self.base_url,
                error=str(e)
            )
            raise

    async def wait_for_completion(
        self,
        task_id: str,
        poll_interval: float = 2.0,
        timeout: float | None = None
    ) -> dict[str, Any]:
        """Wait for task completion by polling status.

        Args:
            task_id: Task ID to wait for
            poll_interval: Seconds between status polls
            timeout: Total timeout in seconds (None = no timeout)

        Returns:
            Final status dict

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
            httpx.HTTPError: If status request fails
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            status = await self.get_status(task_id)

            if status["status"] in ("completed", "failed", "cancelled"):
                logger.info(
                    "agent_task_completed",
                    task_id=task_id,
                    final_status=status["status"],
                    success=status.get("success")
                )
                return status

            # Check timeout
            if timeout is not None:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    logger.error(
                        "agent_wait_timeout",
                        task_id=task_id,
                        elapsed_seconds=elapsed
                    )
                    raise TimeoutError(
                        f"Task {task_id} did not complete within {timeout} seconds"
                    )

            await asyncio.sleep(poll_interval)


async def launch_agent_and_get_client(
    agent_command: list[str],
    startup_timeout: float = 10.0
) -> tuple[asyncio.subprocess.Process, AgentClient]:
    """Launch an agent process and create a client for it.

    This function:
    1. Spawns the agent process
    2. Reads stdout to parse the port
    3. Creates and returns an AgentClient

    Args:
        agent_command: Command to launch agent (e.g., ["python", "-m", "aegis.agents.agent_service"])
        startup_timeout: Seconds to wait for agent to start

    Returns:
        Tuple of (process, client)

    Raises:
        asyncio.TimeoutError: If agent doesn't start in time
        ValueError: If port cannot be parsed from output
    """
    # Launch agent process
    process = await asyncio.create_subprocess_exec(
        *agent_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    logger.info("agent_process_launched", pid=process.pid, command=agent_command)

    try:
        # Read stdout line by line to find port
        port = None
        port_pattern = re.compile(r"AGENT_PORT=(\d+)")

        async def read_port():
            nonlocal port
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                line_str = line.decode().strip()
                match = port_pattern.match(line_str)
                if match:
                    port = int(match.group(1))
                    logger.info("agent_port_detected", port=port, pid=process.pid)
                    return

        # Wait for port with timeout
        await asyncio.wait_for(read_port(), timeout=startup_timeout)

        if port is None:
            raise ValueError("Failed to parse agent port from stdout")

        # Create client
        client = AgentClient(host="127.0.0.1", port=port)

        # Verify agent is healthy
        await asyncio.wait_for(client.health_check(), timeout=5.0)

        logger.info("agent_client_ready", port=port, pid=process.pid)

        return process, client

    except Exception as e:
        # Kill process if startup failed
        logger.error("agent_startup_failed", pid=process.pid, error=str(e))
        process.kill()
        await process.wait()
        raise
