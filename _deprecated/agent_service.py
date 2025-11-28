"""Agent web service for task execution.

This module provides a FastAPI-based web service that runs as a separate process
and handles task execution requests via HTTP API.

Architecture:
- One agent process per task (ephemeral)
- Dynamic port allocation (OS assigns port)
- File-based logging
- Non-blocking task execution
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from aegis.agents.simple_executor import SimpleExecutor
from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaTask
from aegis.config import Settings

logger = structlog.get_logger()


# Request/Response Models
class ExecuteRequest(BaseModel):
    """Request to execute a task."""

    task_gid: str
    project_name: str
    code_path: str | None = None


class ExecuteResponse(BaseModel):
    """Response from execute request."""

    task_id: str  # Same as task_gid for now
    status: str  # "started"
    message: str


class TaskStatus(BaseModel):
    """Status of a running/completed task."""

    task_id: str
    status: str  # "running" | "completed" | "failed"
    started_at: str | None = None
    completed_at: str | None = None
    success: bool | None = None
    output: str | None = None
    error: str | None = None
    log_file: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str  # "healthy"
    agent_type: str
    uptime_seconds: float


# Agent Service
class AgentService:
    """Web service for agent task execution."""

    def __init__(self):
        self.config = Settings()
        self.executor = SimpleExecutor()
        self.asana_client = AsanaClient(self.config.asana_access_token)
        self.app = FastAPI(title="Aegis Agent Service", version="1.0.0")
        self.start_time = datetime.now()

        # Task tracking
        self.current_task: dict[str, Any] | None = None
        self.execution_task: asyncio.Task | None = None

        # Setup routes
        self._setup_routes()

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.post("/execute", response_model=ExecuteResponse)
        async def execute_task(request: ExecuteRequest) -> ExecuteResponse:
            """Execute a task asynchronously."""
            if self.current_task and self.current_task["status"] == "running":
                raise HTTPException(
                    status_code=409,
                    detail="Agent is already executing a task"
                )

            # Fetch task from Asana
            try:
                task = await self.asana_client.get_task(request.task_gid)
            except Exception as e:
                logger.error("failed_to_fetch_task", task_gid=request.task_gid, error=str(e))
                raise HTTPException(
                    status_code=404,
                    detail=f"Failed to fetch task: {str(e)}"
                )

            # Create log file
            logs_dir = Path.cwd() / "logs" / "agents"
            logs_dir.mkdir(parents=True, exist_ok=True)
            log_file = logs_dir / f"{request.task_gid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

            # Initialize task tracking
            self.current_task = {
                "task_id": request.task_gid,
                "task_name": task.name,
                "status": "running",
                "started_at": datetime.now(),
                "completed_at": None,
                "success": None,
                "output": None,
                "error": None,
                "log_file": str(log_file),
            }

            # Start execution in background
            self.execution_task = asyncio.create_task(
                self._execute_task_background(task, request.project_name, request.code_path, log_file)
            )

            logger.info(
                "task_execution_started",
                task_gid=request.task_gid,
                task_name=task.name,
                log_file=str(log_file)
            )

            return ExecuteResponse(
                task_id=request.task_gid,
                status="started",
                message=f"Task '{task.name}' execution started"
            )

        @self.app.get("/status/{task_id}", response_model=TaskStatus)
        async def get_task_status(task_id: str) -> TaskStatus:
            """Get status of a task."""
            if not self.current_task or self.current_task["task_id"] != task_id:
                raise HTTPException(
                    status_code=404,
                    detail=f"Task {task_id} not found"
                )

            return TaskStatus(
                task_id=self.current_task["task_id"],
                status=self.current_task["status"],
                started_at=self.current_task["started_at"].isoformat() if self.current_task["started_at"] else None,
                completed_at=self.current_task["completed_at"].isoformat() if self.current_task["completed_at"] else None,
                success=self.current_task["success"],
                output=self.current_task["output"],
                error=self.current_task["error"],
                log_file=self.current_task["log_file"],
            )

        @self.app.post("/cancel/{task_id}")
        async def cancel_task(task_id: str) -> dict[str, str]:
            """Cancel a running task."""
            if not self.current_task or self.current_task["task_id"] != task_id:
                raise HTTPException(
                    status_code=404,
                    detail=f"Task {task_id} not found"
                )

            if self.current_task["status"] != "running":
                raise HTTPException(
                    status_code=400,
                    detail=f"Task {task_id} is not running (status: {self.current_task['status']})"
                )

            # Cancel the execution task
            if self.execution_task:
                self.execution_task.cancel()

            self.current_task["status"] = "cancelled"
            self.current_task["completed_at"] = datetime.now()
            self.current_task["success"] = False
            self.current_task["error"] = "Task cancelled by user"

            logger.info("task_cancelled", task_id=task_id)

            return {
                "status": "cancelled",
                "message": f"Task {task_id} cancelled"
            }

        @self.app.get("/health", response_model=HealthResponse)
        async def health_check() -> HealthResponse:
            """Health check endpoint."""
            uptime = (datetime.now() - self.start_time).total_seconds()
            return HealthResponse(
                status="healthy",
                agent_type="simple_executor",
                uptime_seconds=uptime
            )

    async def _execute_task_background(
        self,
        task: AsanaTask,
        project_name: str,
        code_path: str | None,
        log_file: Path
    ) -> None:
        """Execute task in background and update status.

        Args:
            task: Asana task to execute
            project_name: Name of the project
            code_path: Path to code directory
            log_file: Path to log file for output
        """
        try:
            # Redirect stdout/stderr to log file
            with open(log_file, "w") as log_fh:
                log_fh.write("=== Aegis Agent Task Execution Log ===\n")
                log_fh.write(f"Task: {task.name}\n")
                log_fh.write(f"Task GID: {task.gid}\n")
                log_fh.write(f"Started: {datetime.now().isoformat()}\n")
                log_fh.write("=" * 50 + "\n\n")
                log_fh.flush()

                # Execute task
                result = await self.executor.execute_task(
                    task=task,
                    project_name=project_name,
                    code_path=code_path
                )

                # Write result to log
                log_fh.write(f"\n\n{'=' * 50}\n")
                log_fh.write(f"Completed: {datetime.now().isoformat()}\n")
                log_fh.write(f"Success: {result['success']}\n")
                if result.get('error'):
                    log_fh.write(f"Error: {result['error']}\n")
                log_fh.flush()

            # Update task status
            self.current_task["status"] = "completed" if result["success"] else "failed"
            self.current_task["completed_at"] = datetime.now()
            self.current_task["success"] = result["success"]
            self.current_task["output"] = result.get("output")
            self.current_task["error"] = result.get("error")

            logger.info(
                "task_execution_completed",
                task_gid=task.gid,
                success=result["success"],
            )

        except asyncio.CancelledError:
            self.current_task["status"] = "cancelled"
            self.current_task["completed_at"] = datetime.now()
            self.current_task["success"] = False
            self.current_task["error"] = "Task cancelled"
            logger.info("task_execution_cancelled", task_gid=task.gid)
            raise

        except Exception as e:
            self.current_task["status"] = "failed"
            self.current_task["completed_at"] = datetime.now()
            self.current_task["success"] = False
            self.current_task["error"] = str(e)
            logger.error("task_execution_failed", task_gid=task.gid, error=str(e), exc_info=True)


def run_agent_service(host: str = "127.0.0.1", port: int = 0) -> None:
    """Run the agent service.

    Args:
        host: Host to bind to
        port: Port to bind to (0 = dynamic allocation)
    """
    import socket

    service = AgentService()

    # If port=0, we need to find an available port first
    if port == 0:
        # Create a socket, bind to get a free port, then close it
        # Uvicorn will reuse this port immediately
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((host, 0))
        port = sock.getsockname()[1]
        sock.close()

    # Print port to stdout BEFORE starting uvicorn (so orchestrator can read it)
    print(f"AGENT_PORT={port}", flush=True)
    logger.info("agent_service_starting", host=host, port=port)

    # Now run uvicorn with the known port
    config = uvicorn.Config(
        service.app,
        host=host,
        port=port,
        log_config=None,  # Disable uvicorn logging, use our own
        access_log=False,
    )
    server = uvicorn.Server(config)

    # Run server using proper API
    asyncio.run(server.serve())


if __name__ == "__main__":
    # Can be run standalone for testing
    run_agent_service()
