"""Rich console display for orchestrator status.

Provides a live-updating display showing active tasks, their status,
and log files being written to.
"""

from datetime import datetime
from typing import Any

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


class OrchestratorDisplay:
    """Live display for orchestrator status."""

    def __init__(self, console: Console | None = None, project_name: str | None = None):
        """Initialize the display.

        Args:
            console: Rich console instance (creates new one if None)
            project_name: Name of the project being monitored (for display)
        """
        self.console = console or Console()
        self.project_name = project_name or "Unknown Project"
        self.active_tasks: dict[str, dict[str, Any]] = {}
        self.stats = {
            "total_dispatched": 0,
            "completed": 0,
            "failed": 0,
            "launched": 0,
        }
        self.orchestrator_status = "stopped"
        self.orchestrator_pid: int | None = None
        self.last_poll_time: datetime | None = None

    def update_orchestrator_status(
        self,
        status: str,
        pid: int | None = None,
        last_poll_time: datetime | None = None,
    ) -> None:
        """Update orchestrator status.

        Args:
            status: Current status (running, stopped, etc.)
            pid: Process ID
            last_poll_time: Time of last poll
        """
        self.orchestrator_status = status
        self.orchestrator_pid = pid
        self.last_poll_time = last_poll_time

    def add_task(
        self,
        task_gid: str,
        task_name: str,
        status: str = "dispatched",
        log_file: str | None = None,
        started_at: datetime | None = None,
    ) -> None:
        """Add a task to the display.

        Args:
            task_gid: Task GID
            task_name: Task name
            status: Task status
            log_file: Path to log file (if any)
            started_at: When task started
        """
        self.active_tasks[task_gid] = {
            "name": task_name,
            "status": status,
            "log_file": log_file,
            "started_at": started_at or datetime.now(),
        }
        self.stats["total_dispatched"] += 1

    def update_task_status(
        self,
        task_gid: str,
        status: str,
        log_file: str | None = None,
    ) -> None:
        """Update task status.

        Args:
            task_gid: Task GID
            status: New status
            log_file: Updated log file path (if any)
        """
        if task_gid in self.active_tasks:
            self.active_tasks[task_gid]["status"] = status
            if log_file:
                self.active_tasks[task_gid]["log_file"] = log_file

    def remove_task(self, task_gid: str, final_status: str = "completed") -> None:
        """Remove a task from the display.

        Args:
            task_gid: Task GID
            final_status: Final status (completed, failed, etc.)
        """
        if task_gid in self.active_tasks:
            del self.active_tasks[task_gid]

            # Update stats
            if final_status == "completed":
                self.stats["completed"] += 1
            elif final_status == "failed":
                self.stats["failed"] += 1
            elif final_status == "launched":
                self.stats["launched"] += 1

    def _create_header(self) -> Panel:
        """Create header panel with orchestrator status."""
        status_color = "green" if self.orchestrator_status == "running" else "red"

        # Build status line
        status_text = Text()
        status_text.append("Aegis Orchestrator ", style="bold")
        status_text.append(f"[{self.orchestrator_status.upper()}]", style=f"bold {status_color}")
        if self.orchestrator_pid:
            status_text.append(f" (PID: {self.orchestrator_pid})", style="dim")
        status_text.append("\n")

        # Add project line
        status_text.append("Project: ", style="bold")
        status_text.append(self.project_name, style="cyan")

        # Add last poll time if available
        if self.last_poll_time:
            status_text.append("\n")
            status_text.append(f"Last Poll: {self.last_poll_time.strftime('%H:%M:%S')}", style="dim")

        return Panel(
            status_text,
            title="Status",
            border_style=status_color,
        )

    def _create_stats_panel(self) -> Panel:
        """Create statistics panel."""
        stats_text = Text()
        stats_text.append("Dispatched: ", style="bold")
        stats_text.append(f"{self.stats['total_dispatched']}\n")
        stats_text.append("Completed: ", style="bold green")
        stats_text.append(f"{self.stats['completed']}\n", style="green")
        stats_text.append("Failed: ", style="bold red")
        stats_text.append(f"{self.stats['failed']}\n", style="red")
        stats_text.append("Launched: ", style="bold cyan")
        stats_text.append(f"{self.stats['launched']}", style="cyan")

        return Panel(stats_text, title="Statistics", border_style="blue")

    def _create_tasks_table(self) -> Table:
        """Create table of active tasks."""
        table = Table(title="Active Tasks", show_header=True, header_style="bold magenta")
        table.add_column("Task", style="cyan", width=40)
        table.add_column("Status", style="yellow", width=12)
        table.add_column("Duration", style="green", width=10)
        table.add_column("Log File", style="blue", width=50)

        if not self.active_tasks:
            table.add_row("No active tasks", "", "", "")
            return table

        # Sort by start time (oldest first)
        sorted_tasks = sorted(
            self.active_tasks.items(),
            key=lambda x: x[1]["started_at"],
        )

        for _task_gid, task_info in sorted_tasks:
            # Calculate duration
            duration = datetime.now() - task_info["started_at"]
            duration_str = f"{int(duration.total_seconds())}s"

            # Truncate task name if too long
            task_name = task_info["name"]
            if len(task_name) > 37:
                task_name = task_name[:34] + "..."

            # Get status with color
            status = task_info["status"]
            status_style = {
                "dispatched": "yellow",
                "in_progress": "cyan",
                "launching": "magenta",
                "running": "green",
            }.get(status, "white")

            # Get log file
            log_file = task_info.get("log_file") or "N/A"
            if len(log_file) > 47:
                # Show last part of path
                log_file = "..." + log_file[-44:]

            table.add_row(
                task_name,
                Text(status, style=status_style),
                duration_str,
                log_file,
            )

        return table

    def render(self) -> Layout:
        """Render the current display.

        Returns:
            Rich Layout with all components
        """
        layout = Layout()

        # Create top section with header and stats side by side
        top_layout = Layout(name="top", size=8)
        top_layout.split_row(
            Layout(self._create_header(), name="header"),
            Layout(self._create_stats_panel(), name="stats", size=30),
        )

        # Create main layout
        layout.split_column(
            top_layout,
            Layout(Panel(self._create_tasks_table(), border_style="green"), name="tasks"),
        )

        return layout

    def create_live_display(self) -> Live:
        """Create a Live display for real-time updates.

        Returns:
            Rich Live instance
        """
        return Live(
            self.render(),
            console=self.console,
            refresh_per_second=2,
            screen=True,  # Use alternate screen to avoid log interference
        )
