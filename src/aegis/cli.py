"""Command-line interface for Aegis."""

import asyncio
import sys

import asana.rest
import click
import structlog
from rich.console import Console
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from aegis.config import get_settings
from aegis.database.session import cleanup_db_connections
from aegis.database.state import (
    mark_in_progress_tasks_interrupted_async,
    mark_orchestrator_running,
    mark_orchestrator_stopped_async,
)
from aegis.utils.shutdown import get_shutdown_handler


class SmartConsole:
    """Console wrapper that can be disabled and falls back to plain print."""

    def __init__(self):
        self._console = Console()
        self._enabled = True

    def set_enabled(self, enabled: bool):
        """Enable or disable rich console output."""
        self._enabled = enabled

    def print(self, *args, **kwargs):
        """Print using rich console if enabled, plain print otherwise."""
        if self._enabled:
            self._console.print(*args, **kwargs)
        else:
            # Strip rich markup and use plain print
            if args:
                message = str(args[0])
                # Simple markup removal
                import re
                message = re.sub(r'\[/?[^\]]+\]', '', message)
                print(message)
            else:
                print()

    def __getattr__(self, name):
        """Delegate all other methods to the real console."""
        return getattr(self._console, name)


console = SmartConsole()
logger = structlog.get_logger()


def parse_task_gid(task_input: str) -> str:
    """Parse task GID from either a GID string or Asana URL.

    Args:
        task_input: Either a task GID or an Asana URL

    Returns:
        Task GID

    Examples:
        >>> parse_task_gid("1212085457078218")
        '1212085457078218'
        >>> parse_task_gid("https://app.asana.com/0/1212085431574340/1212085457078218")
        '1212085457078218'
    """
    import re

    # If it looks like a URL, extract the task GID
    if "asana.com" in task_input:
        # Try pattern for /task/{gid} format first
        match = re.search(r'/task/(\d+)', task_input)
        if match:
            return match.group(1)

        # For standard Asana URLs like https://app.asana.com/0/{project_gid}/{task_gid}
        # The task GID is the last long number in the path
        # Remove query params and fragments first
        url_path = task_input.split('?')[0].split('#')[0]

        # Find all numbers with 13+ digits (Asana GIDs)
        numbers = re.findall(r'\d{13,}', url_path)
        if numbers:
            # Return the last one (should be the task GID)
            return numbers[-1]

        raise ValueError(f"Could not extract task GID from URL: {task_input}")

    # Otherwise assume it's already a GID
    return task_input.strip()


def parse_project_gid(project_input: str) -> str | None:
    """Parse project GID from either a GID string or Asana URL.

    If the input looks like a numeric GID or URL, returns the GID.
    If it looks like a name (non-numeric), returns None to indicate name-based lookup is needed.

    Args:
        project_input: Either a project GID, Asana URL, or project name

    Returns:
        Project GID if input is GID/URL, None if it's a name

    Examples:
        >>> parse_project_gid("1212085431574340")
        '1212085431574340'
        >>> parse_project_gid("https://app.asana.com/0/1212085431574340")
        '1212085431574340'
        >>> parse_project_gid("Aegis")
        None
    """
    import re

    project_input = project_input.strip()

    # If it looks like a URL, extract the project GID
    if "asana.com" in project_input:
        # For standard Asana URLs like https://app.asana.com/0/{project_gid}
        # Remove query params and fragments first
        url_path = project_input.split('?')[0].split('#')[0]

        # Find all numbers with 13+ digits (Asana GIDs)
        numbers = re.findall(r'\d{13,}', url_path)
        if numbers:
            # Return the first one after the /0/ (should be the project GID)
            return numbers[0] if len(numbers) >= 1 else numbers[-1]

        raise ValueError(f"Could not extract project GID from URL: {project_input}")

    # If it's all digits (a GID), return it
    if project_input.isdigit():
        return project_input

    # Otherwise it's a project name, return None to indicate name lookup needed
    return None


def launch_in_hyper_terminal(command: list[str], cwd: str | None = None) -> int:
    """Launch a command in a new Hyper terminal that auto-exits on completion.

    Args:
        command: Command and arguments to run
        cwd: Working directory for the command

    Returns:
        Exit code from the command
    """
    import shlex
    import subprocess
    import tempfile

    # Create a temporary script file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
        f.write("#!/bin/bash\n")
        f.write("set -e\n\n")

        if cwd:
            f.write(f"cd {shlex.quote(cwd)}\n")

        # Write the actual command
        cmd_str = " ".join(shlex.quote(arg) for arg in command)
        f.write(f"{cmd_str}\n")

        script_path = f.name

    # Make script executable
    subprocess.run(["chmod", "+x", script_path], check=True)

    # AppleScript to launch Hyper with the script
    # The terminal will auto-exit when the command completes
    applescript = f"""
    tell application "Hyper"
        activate
        delay 0.5
        tell application "System Events"
            keystroke "t" using command down
            delay 0.3
            keystroke "{script_path}; rm {script_path}; exit"
            keystroke return
        end tell
    end tell
    """

    # Execute the AppleScript
    subprocess.run(
        ["osascript", "-e", applescript],
        check=True
    )

    # Note: We can't easily wait for the Hyper terminal command to complete
    # or get its exit code, so we return 0 immediately
    # The terminal will close automatically when the command finishes
    # The script will clean up after itself
    return 0


@click.group()
@click.version_option(version="0.1.0")
@click.option(
    "--console/--no-console",
    "use_console",
    default=True,
    help="Use rich console formatting (default: true)",
    is_flag=True,
)
@click.pass_context
def main(ctx: click.Context, use_console: bool) -> None:
    """Aegis - Intelligent assistant orchestration system."""
    # Store in context for all commands to access
    ctx.ensure_object(dict)
    ctx.obj["console_enabled"] = use_console

    # Set global console state
    console.set_enabled(use_console)


@main.command()
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
def config(use_console: bool) -> None:
    """Display current configuration."""
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    try:
        settings = get_settings()
        console.print("[bold]Aegis Configuration[/bold]")
        console.print(f"Asana Workspace: {settings.asana_workspace_gid}")
        console.print(f"Asana Portfolio: {settings.asana_portfolio_gid}")
        console.print(f"Claude Model: {settings.anthropic_model}")
        console.print(f"Poll Interval: {settings.poll_interval_seconds}s")
        console.print(f"Max Concurrent Tasks: {settings.max_concurrent_tasks}")
        console.print(f"Vector DB Enabled: {settings.enable_vector_db}")
        console.print(f"Multi-Agent Enabled: {settings.enable_multi_agent}")
    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        sys.exit(1)


@main.command()
@click.option("--projects-only", is_flag=True, help="Only sync projects, not tasks")
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
def sync(projects_only: bool, use_console: bool) -> None:
    """Sync Asana projects and tasks into local database.

    Fetches all projects from the configured portfolio and syncs them to the database.
    By default, also syncs all tasks for each project.

    This is idempotent - re-running will update existing records.

    Examples:
        aegis sync                    # Sync all projects and tasks
        aegis sync --projects-only    # Only sync projects, skip tasks
    """
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    console.print("[bold]Starting Asana Sync...[/bold]")

    async def _sync() -> None:
        from aegis.asana.client import AsanaClient
        from aegis.sync.asana_sync import sync_portfolio_projects, sync_project_tasks

        try:
            settings = get_settings()
            client = AsanaClient(settings.asana_access_token)

            console.print(f"[cyan]Syncing projects from portfolio {settings.asana_portfolio_gid}...[/cyan]")

            # Sync projects
            from aegis.database.session import get_db_session
            with get_db_session() as session:
                projects = await sync_portfolio_projects(
                    client=client,
                    portfolio_gid=settings.asana_portfolio_gid,
                    workspace_gid=settings.asana_workspace_gid,
                    session=session,
                )

                console.print(f"[green]✓[/green] Synced {len(projects)} projects")

                if not projects_only:
                    # Sync tasks for each non-archived project
                    total_tasks = 0
                    for project in projects:
                        if not project.archived:
                            console.print(f"[cyan]Syncing tasks for project: {project.name}...[/cyan]")
                            tasks = await sync_project_tasks(
                                client=client,
                                project=project,
                                session=session,
                            )
                            console.print(f"[green]✓[/green] Synced {len(tasks)} tasks from {project.name}")
                            total_tasks += len(tasks)

                    console.print(f"\n[bold green]✓ Sync completed:[/bold green] {len(projects)} projects, {total_tasks} tasks")
                else:
                    console.print(f"\n[bold green]✓ Projects sync completed:[/bold green] {len(projects)} projects")

        except Exception as e:
            console.print(f"[red]✗ Sync failed: {e}[/red]")
            logger.error("sync_failed", error=str(e))
            sys.exit(1)

    asyncio.run(_sync())


@main.command()
@click.argument("project")
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
@click.option("--auto-dispatch/--no-auto-dispatch", "auto_dispatch", default=False, help="Automatically dispatch tasks (default: false - manual mode)")
@click.pass_context
def start(ctx: click.Context, project: str, use_console: bool, auto_dispatch: bool) -> None:
    """Start the Aegis orchestrator for a specific project.

    By default, the orchestrator operates in MANUAL mode - tasks are displayed on the
    web dashboard with "Run" buttons. Click a button to execute a task.

    Use --auto-dispatch to enable automatic task execution (legacy behavior).

    PROJECT can be a project name, GID, or Asana URL.

    Examples:
        aegis start Aegis                    # Manual mode (default)
        aegis start Aegis --auto-dispatch    # Auto-dispatch mode
        aegis start 1212085431574340
        aegis start https://app.asana.com/0/1212085431574340
    """
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    console.print("[bold green]Starting Aegis Orchestrator...[/bold green]")

    async def _start() -> None:
        import asana

        from aegis.orchestrator.main import Orchestrator

        try:
            settings = get_settings()

            # Parse project input
            project_gid = parse_project_gid(project)

            # If project_gid is None, we need to look up by name
            if project_gid is None:
                console.print(f"[bold]Resolving project '{project}'...[/bold]")

                # Configure API client
                configuration = asana.Configuration()
                configuration.access_token = settings.asana_access_token
                api_client = asana.ApiClient(configuration)
                portfolios_api = asana.PortfoliosApi(api_client)

                # Get projects from portfolio
                projects_generator = await asyncio.to_thread(
                    portfolios_api.get_items_for_portfolio,
                    settings.asana_portfolio_gid,
                    {"opt_fields": "name,gid"}
                )
                projects_list = list(projects_generator)

                # Find matching project (case-insensitive)
                matching_project = None
                for proj in projects_list:
                    if proj["name"].lower() == project.lower():
                        matching_project = proj
                        break

                if not matching_project:
                    console.print(f"[red]✗ Project '{project}' not found in portfolio[/red]")
                    console.print("\n[dim]Available projects:[/dim]")
                    for proj in projects_list:
                        console.print(f"  • {proj['name']} (GID: {proj['gid']})")
                    sys.exit(1)

                project_gid = matching_project["gid"]
                task_or_project = matching_project["name"]
            else:
                # Fetch project details to get the name
                console.print(f"[bold]Fetching project details (GID: {project_gid})...[/bold]")
                configuration = asana.Configuration()
                configuration.access_token = settings.asana_access_token
                api_client = asana.ApiClient(configuration)
                projects_api = asana.ProjectsApi(api_client)

                project_details = await asyncio.to_thread(
                    projects_api.get_project,
                    project_gid,
                    {"opt_fields": "name,gid"}
                )
                task_or_project = project_details.get("name", "Unknown")

            console.print(f"[green]✓[/green] Monitoring project: {task_or_project} (GID: {project_gid})\n")

            # Display configuration
            console.print("[bold]Configuration:[/bold]")
            console.print(f"  Project: {task_or_project}")
            console.print(f"  Project GID: {project_gid}")
            console.print(f"  Poll Interval: {settings.poll_interval_seconds}s")
            console.print(f"  Max Concurrent Tasks: {settings.max_concurrent_tasks}")
            console.print(f"  Shutdown Timeout: {settings.shutdown_timeout}s")
            console.print(f"  Mode: {'Auto-Dispatch' if auto_dispatch else 'Manual (Dashboard)'}\n")

            # Create and run orchestrator with project_gid
            orchestrator = Orchestrator(
                settings,
                project_gid=project_gid,
                project_name=task_or_project,
                use_live_display=use_console,
                auto_dispatch=auto_dispatch
            )
            console.print("[green]✓[/green] Orchestrator initialized")
            console.print("[dim]Press Ctrl+C to stop gracefully[/dim]\n")

            await orchestrator.run()

        except KeyboardInterrupt:
            console.print("\n[yellow]Shutdown signal received...[/yellow]")
        except Exception as e:
            console.print(f"[red]Fatal error: {e}[/red]")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    try:
        asyncio.run(_start())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)  # Standard exit code for SIGINT


@main.command()
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
def test_asana(use_console: bool) -> None:
    """Test Asana API connection and list portfolio projects."""
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    async def _test() -> None:
        import asana

        try:
            settings = get_settings()
            portfolio_gid = settings.asana_portfolio_gid

            console.print(f"[bold]Testing Asana connection to portfolio: {portfolio_gid}[/bold]\n")

            # Configure API client
            configuration = asana.Configuration()
            configuration.access_token = settings.asana_access_token
            api_client = asana.ApiClient(configuration)
            portfolios_api = asana.PortfoliosApi(api_client)

            # Test fetching portfolio
            console.print("Fetching portfolio details...")
            portfolio_dict = await asyncio.to_thread(
                portfolios_api.get_portfolio, portfolio_gid, {"opt_fields": "name"}
            )
            console.print(f"[green]✓[/green] Portfolio: {portfolio_dict['name']}\n")

            # Get projects in portfolio
            console.print("Fetching projects in portfolio...")
            projects_generator = await asyncio.to_thread(
                portfolios_api.get_items_for_portfolio, portfolio_gid, {"opt_fields": "name,gid"}
            )
            projects_list = list(projects_generator)

            if projects_list:
                console.print(f"[green]✓[/green] Found {len(projects_list)} projects\n")
                console.print("First 5 projects:")
                for project_dict in projects_list[:5]:
                    console.print(f"  - {project_dict['name']} (GID: {project_dict['gid']})")
            else:
                console.print("[yellow]No projects in portfolio yet[/yellow]")
                console.print(
                    "\nAdd projects to portfolio at: "
                    f"https://app.asana.com/0/portfolio/{portfolio_gid}"
                )

            console.print("\n[bold green]Asana API connection successful![/bold green]")

        except Exception as e:
            console.print(f"[red]Error testing Asana connection: {e}[/red]")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    asyncio.run(_test())


@main.command()
def test_claude() -> None:
    """Test Claude API connection."""
    console.print("[bold]Testing Claude API connection...[/bold]")
    console.print("[yellow]Note: Claude client not yet implemented[/yellow]")
    # TODO: Implement Claude client test


@main.command()
@click.argument("task_or_project")
@click.option("--agent-name", default="aegis-do", help="Name of the agent for tracking")
@click.option("--prompt", help="Additional prompt/instructions for the agent")
@click.option("--log", help="Path to log file (auto-generated if not specified)")
@click.option("--timeout", type=int, default=1800, help="Execution timeout in seconds (default: 1800 = 30 min)")
@click.option("--terminal/--no-terminal", default=False, help="Launch in new terminal window")
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
def do(task_or_project: str, agent_name: str, prompt: str | None, log: str | None, timeout: int, terminal: bool, use_console: bool) -> None:
    """Execute a task from Asana using Claude Code CLI.

    TASK_OR_PROJECT can be:
    - A task GID (e.g., 1212085457078218)
    - A task URL (e.g., https://app.asana.com/0/1212085431574340/1212085457078218)
    - A project name (e.g., "Aegis") - executes first incomplete task

    This command:
    1. Fetches the task from Asana
    2. Moves task to "In Progress" section
    3. Executes using Claude Code CLI
    4. Posts results and updates task status
    5. Moves to "Implemented" on success

    Examples:
        aegis do 1212085457078218
        aegis do https://app.asana.com/0/1212085431574340/1212085457078218
        aegis do Aegis
    """
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((asana.rest.ApiException, ConnectionError)),
        reraise=True,
    )
    async def post_asana_comment(stories_api, comment_data: dict, task_gid: str) -> None:
        """Post a comment to Asana with retry logic."""
        await asyncio.to_thread(
            stories_api.create_story_for_task,
            comment_data,
            task_gid,
            {},
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((asana.rest.ApiException, ConnectionError)),
        reraise=True,
    )
    async def fetch_with_retry(api_call, *args, **kwargs):
        """Fetch from Asana API with retry logic."""
        return await asyncio.to_thread(api_call, *args, **kwargs)

    async def _do() -> None:
        import os
        import subprocess

        import asana

        # Initialize shutdown handler
        shutdown_handler = get_shutdown_handler(shutdown_timeout=300)
        shutdown_handler.install_signal_handlers()

        # Register cleanup callbacks
        shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
        shutdown_handler.register_cleanup_callback(cleanup_db_connections)

        try:
            settings = get_settings()
            portfolio_gid = settings.asana_portfolio_gid

            # Detect if input is a task GID/URL or project name
            is_task_gid = False
            task_gid_to_execute = None

            # Check if it looks like a task (URL or numeric GID)
            if "asana.com" in task_or_project or task_or_project.isdigit():
                try:
                    task_gid_to_execute = parse_task_gid(task_or_project)
                    is_task_gid = True
                    console.print(f"[bold]Executing task GID: {task_gid_to_execute}[/bold]")
                except:
                    pass

            if not is_task_gid:
                console.print(f"[bold]Finding first task in project '{task_or_project}'...[/bold]")

            # Configure API client
            configuration = asana.Configuration()
            configuration.access_token = settings.asana_access_token
            api_client = asana.ApiClient(configuration)
            portfolios_api = asana.PortfoliosApi(api_client)
            projects_api = asana.ProjectsApi(api_client)
            tasks_api = asana.TasksApi(api_client)
            stories_api = asana.StoriesApi(api_client)

            # Handle project name case
            if not is_task_gid:
                # Get projects from portfolio
                projects_generator = await fetch_with_retry(
                    portfolios_api.get_items_for_portfolio, portfolio_gid, {"opt_fields": "name,gid"}
                )
                projects_list = list(projects_generator)

                # Find matching project (case-insensitive)
                project = None
                for proj in projects_list:
                    if proj["name"].lower() == task_or_project.lower():
                        project = proj
                        break

                if not project:
                    console.print(f"[red]Error: Project '{task_or_project}' not found in portfolio[/red]")
                    console.print("\nAvailable projects:")
                    for proj in projects_list:
                        console.print(f"  - {proj['name']}")
                    sys.exit(1)

                console.print(f"[green]✓[/green] Found project: {project['name']} (GID: {project['gid']})\n")

                # Get project details to find code path
                project_details = await fetch_with_retry(
                    projects_api.get_project, project["gid"], {"opt_fields": "name,notes"}
                )

                # Extract code path from notes
                code_path = None
                if project_details.get("notes"):
                    for line in project_details["notes"].split("\n"):
                        if line.startswith("Code Location:"):
                            code_path = line.split(":", 1)[1].strip()
                            code_path = os.path.expanduser(code_path)
                            break

                # Get tasks from project
                console.print("Fetching tasks...")
                tasks_generator = await fetch_with_retry(
                    tasks_api.get_tasks_for_project,
                    project["gid"],
                    {"opt_fields": "name,notes,completed,gid,permalink_url"},
                )
                tasks_list = list(tasks_generator)

                # Find first incomplete task
                first_task = None
                for task in tasks_list:
                    if not task.get("completed", False):
                        first_task = task
                        break

                if not first_task:
                    console.print("[yellow]No incomplete tasks found in this project[/yellow]")
                    sys.exit(0)

                console.print(f"[green]✓[/green] First incomplete task: {first_task['name']}\n")
                console.print(f"[dim]Task URL: {first_task.get('permalink_url', 'N/A')}[/dim]\n")
            else:
                # Handle direct task GID case
                console.print("Fetching task...")
                task_data = await fetch_with_retry(
                    tasks_api.get_task,
                    task_gid_to_execute,
                    {"opt_fields": "name,notes,completed,gid,permalink_url,projects.name"},
                )
                first_task = task_data

                # Get project from task
                if not task_data.get("projects"):
                    console.print("[red]Error: Task is not in any project[/red]")
                    sys.exit(1)

                project = task_data["projects"][0]
                console.print(f"[green]✓[/green] Task: {first_task['name']}")
                console.print(f"[green]✓[/green] Project: {project['name']}\n")

                # Get project details for code path
                project_details = await fetch_with_retry(
                    projects_api.get_project, project["gid"], {"opt_fields": "name,notes"}
                )

                # Extract code path
                code_path = None
                if project_details.get("notes"):
                    for line in project_details["notes"].split("\n"):
                        if line.startswith("Code Location:"):
                            code_path = line.split(":", 1)[1].strip()
                            code_path = os.path.expanduser(code_path)
                            break

            # Fetch existing question tasks to prevent duplicates
            existing_questions_list = []
            try:
                all_project_tasks = await fetch_with_retry(
                    tasks_api.get_tasks_for_project,
                    project["gid"],
                    {"opt_fields": "name,gid,completed"}
                )
                for task in all_project_tasks:
                    task_dict = task if isinstance(task, dict) else task.to_dict()
                    if task_dict.get("name", "").startswith("Question:") and not task_dict.get("completed", False):
                        existing_questions_list.append(task_dict["name"])
            except Exception as e:
                logger.warning("failed_to_fetch_existing_questions", error=str(e))

            # Format task context for Claude CLI
            task_context = f"""Task: {first_task['name']}

Project: {project['name']}"""

            if code_path:
                task_context += f"\nCode Location: {code_path}"

            if existing_questions_list:
                task_context += "\n\nExisting Question Tasks (DO NOT CREATE DUPLICATES):\n" + "\n".join(f"  - {q}" for q in existing_questions_list)

            if first_task.get("notes"):
                task_context += f"\n\nTask Description:\n{first_task['notes']}"

            task_context += """

IMPORTANT: You are running in HEADLESS mode.

- Do not ask the user questions or wait for input
- If you need clarification, CHECK THE "Existing Question Tasks" LIST ABOVE FIRST
- Only create a NEW Question task if it doesn't already exist (exact name match required)
- Question task format: "Question: [specific question]" (must start with "Question: ")
- Use the Asana API to create question tasks and add them as dependencies to blocked tasks
- When you have completed this task, provide a summary and EXIT
- Do not wait for further input"""

            # Determine working directory
            working_dir = code_path if code_path and os.path.isdir(code_path) else None

            # Set up logging
            from datetime import datetime
            from pathlib import Path

            # Get the task GID for the log filename
            task_gid = first_task['gid']

            # Setup logging with unique filename
            if log:
                # If log path is explicitly provided, use it
                log_file = Path(log)
            else:
                # Generate unique log filename: agent-<agent_name>-<task_gid>-<pid>-<timestamp>.log
                timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                pid = os.getpid()
                log_filename = f"agent-{agent_name}-{task_gid}-{pid}-{timestamp_str}.log"
                log_file = Path("logs") / log_filename

            logs_dir = log_file.parent
            logs_dir.mkdir(exist_ok=True, parents=True)
            timestamp = datetime.now().isoformat()

            console.print("[bold]Executing task with Claude CLI...[/bold]\n")
            console.print(f"[dim]Task: {first_task['name']}[/dim]")
            console.print(f"[dim]Working directory: {working_dir or 'current directory'}[/dim]")
            console.print(f"[dim]Logging to: {log_file}[/dim]\n")
            console.print("[dim]" + "=" * 60 + "[/dim]\n")

            try:
                # Run claude - either in terminal or with output capture
                if terminal:
                    # Launch in Hyper terminal (auto-exits on completion)
                    console.print("[cyan]Launching Claude Code in new Hyper terminal...[/cyan]\n")
                    launch_in_hyper_terminal(
                        ["claude", "--dangerously-skip-permissions", task_context],
                        cwd=working_dir
                    )
                    # Note: Can't capture output or track subprocess with terminal mode
                    # Return early since terminal handles execution
                    console.print("[dim]Task running in terminal - check Hyper window for progress[/dim]")
                    return

                # Headless execution with live progress
                console.print("[dim]Running with live output...[/dim]\n")
                console.print(f"[dim]Log file: {log_file}[/dim]")
                console.print("[dim]" + "─" * 60 + "[/dim]\n")

                # Open log file for writing (line buffered)
                log_file_handle = open(log_file, "a", buffering=1)
                log_file_handle.write(f"\n{'='*80}\n")
                log_file_handle.write(f"Task: {first_task['name']} ({task_gid})\n")
                log_file_handle.write(f"Agent: {agent_name}\n")
                log_file_handle.write(f"Started: {timestamp}\n")
                log_file_handle.write(f"{'='*80}\n")
                log_file_handle.flush()

                try:
                    # Start subprocess with stdout going to log file
                    process = subprocess.Popen(
                        ["claude", "--dangerously-skip-permissions", task_context],
                        cwd=working_dir,
                        stdout=log_file_handle,
                        stderr=subprocess.PIPE,
                        text=True,
                        env={**os.environ, "PYTHONUNBUFFERED": "1"},
                    )

                    # Track subprocess for shutdown handling
                    shutdown_handler.track_subprocess(process)

                    # Monitor progress by tailing the log file
                    import threading
                    import time

                    def tail_log():
                        with open(log_file) as f:
                            f.seek(0, 2)  # Skip to end
                            while process.poll() is None:
                                line = f.readline()
                                if line:
                                    console.print(line.rstrip())
                                else:
                                    time.sleep(0.1)
                            # Read remaining lines
                            for line in f:
                                console.print(line.rstrip())

                    tail_thread = threading.Thread(target=tail_log, daemon=True)
                    tail_thread.start()

                    try:
                        _, stderr = process.communicate(timeout=timeout)
                        success = (process.returncode == 0)
                        tail_thread.join(timeout=2)

                        log_file_handle.write(f"\n{'='*80}\n")
                        log_file_handle.write(f"Completed: {datetime.now().isoformat()}\n")
                        log_file_handle.write(f"Return code: {process.returncode}\n")
                        if stderr:
                            log_file_handle.write(f"\nSTDERR:\n{stderr}\n")
                        log_file_handle.write(f"{'='*80}\n")
                        log_file_handle.flush()

                        # Read output from log file
                        with open(log_file) as f:
                            output = f.read()

                    except subprocess.TimeoutExpired:
                        console.print(f"\n[red]✗ Execution timeout after {timeout} seconds[/red]")
                        console.print("[yellow]Suggestions:[/yellow]")
                        console.print(f"  • Increase timeout: --timeout {timeout * 2}")
                        console.print("  • Check if task is too complex for single execution")
                        console.print(f"  • Review partial output in log: {log_file}")

                        process.kill()
                        _, stderr = process.communicate()
                        log_file_handle.write(f"\n\nTIMEOUT after {timeout}s\n")
                        if stderr:
                            log_file_handle.write(f"STDERR:\n{stderr}\n")
                        log_file_handle.flush()
                        success = False

                        with open(log_file) as f:
                            output = f.read()

                finally:
                    shutdown_handler.untrack_subprocess(process)
                    log_file_handle.close()

                console.print("\n" + "[dim]" + "─" * 60 + "[/dim]\n")

                # Post comment to Asana
                console.print("Posting results to Asana...")

                status_emoji = "✅" if success else "⚠️"
                status_text = "completed" if success else f"completed with errors (exit code {process.returncode})"

                comment_text = f"""{status_emoji} Task {status_text} via Aegis

**Agent**: {agent_name}
**Timestamp**: {timestamp}

**Output**:
```
{output[:60000] if output else '(No output captured)'}
```

**Log file**: `{log_file}`

---
*Executed by Aegis orchestration system*
"""

                comment_data = {"data": {"text": comment_text}}

                try:
                    await post_asana_comment(stories_api, comment_data, first_task["gid"])
                    console.print("[green]✓[/green] Comment posted to Asana\n")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Failed to post comment: {e}\n")

                if success:
                    # Mark task as complete and move to appropriate section
                    try:
                        from aegis.asana.client import AsanaClient
                        asana_client = AsanaClient(settings.asana_access_token)

                        # Check if this is a question task
                        is_question = first_task['name'].lower().startswith("question:")

                        if is_question:
                            # Move to Answered section
                            await asana_client.complete_task_and_move_to_answered(
                                first_task["gid"],
                                project["gid"]
                            )
                            console.print("[green]✓[/green] Task marked complete and moved to Answered\n")
                        else:
                            # Move to Implemented section
                            await asana_client.complete_task_and_move_to_implemented(
                                first_task["gid"],
                                project["gid"]
                            )
                            console.print("[green]✓[/green] Task marked complete and moved to Implemented\n")
                        console.print("[bold green]✓ Task execution completed[/bold green]\n")
                    except Exception as e:
                        logger.warning("failed_to_complete_task", task_gid=first_task["gid"], error=str(e))
                        console.print(f"[yellow]⚠[/yellow] Failed to mark complete/move: {e}\n")
                else:
                    # Task failed - move to Failed section but don't mark complete
                    console.print(
                        f"[red]✗ Task failed with exit code {result.returncode}[/red]\n"
                    )
                    try:
                        from aegis.asana.client import AsanaClient
                        asana_client = AsanaClient(settings.asana_access_token)

                        # Get sections
                        sections = await asana_client.get_sections(project["gid"])
                        section_map = {s.name: s.gid for s in sections}

                        if "Failed" in section_map:
                            await asana_client.move_task_to_section(
                                first_task["gid"],
                                project["gid"],
                                section_map["Failed"]
                            )
                            console.print("[yellow]→ Moved to Failed section[/yellow]\n")
                        else:
                            console.print("[yellow]⚠ 'Failed' section not found - task left in current section[/yellow]\n")
                    except Exception as e:
                        logger.warning("failed_to_move_task", task_gid=first_task["gid"], error=str(e))
                        console.print(f"[yellow]⚠ Could not move to Failed: {e}[/yellow]\n")

            except FileNotFoundError:
                console.print("[red]Error: 'claude' CLI not found. Please install it first.[/red]")
                console.print("Install: npm install -g @anthropic-ai/claude-cli\n")
                sys.exit(1)

            except Exception as e:
                console.print(f"[red]Unexpected error: {e}[/red]\n")
                import traceback
                traceback.print_exc()

        except Exception as e:
            console.print(f"[red]Critical error: {e}[/red]")
            import traceback

            traceback.print_exc()
            console.print("[yellow]Command failed but not exiting to allow continued operation[/yellow]")
            # Don't sys.exit(1) - be robust
        finally:
            # Always run shutdown sequence
            try:
                await shutdown_handler.shutdown()
                console.print("\n[dim]Shutdown complete[/dim]")
            except Exception as e:
                logger.error("shutdown_failed", error=str(e), exc_info=True)
                console.print(f"[red]Warning: Shutdown encountered errors: {e}[/red]")

    try:
        asyncio.run(_do())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)  # Standard exit code for SIGINT


@main.command()
@click.argument("task_or_project")
@click.option("--max-tasks", default=5, help="Maximum tasks to execute in one session")
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.option("--terminal/--no-terminal", default=True, help="Launch Claude Code in a new Hyper terminal (default: true)")
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
@click.option("--timeout", type=int, default=1800, help="Execution timeout per task in seconds (default: 1800 = 30 min)")
def work_on(task_or_project: str, max_tasks: int, dry_run: bool, terminal: bool, use_console: bool, timeout: int) -> None:
    """Autonomous work on a project - assess state, ask questions, do ready tasks."""
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((asana.rest.ApiException, ConnectionError)),
        reraise=True,
    )
    async def post_asana_comment(stories_api, comment_data: dict, task_gid: str) -> None:
        """Post a comment to Asana with retry logic."""
        await asyncio.to_thread(
            stories_api.create_story_for_task,
            comment_data,
            task_gid,
            {},
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((asana.rest.ApiException, ConnectionError)),
        reraise=True,
    )
    async def fetch_with_retry(api_call, *args, **kwargs):
        """Fetch from Asana API with retry logic."""
        return await asyncio.to_thread(api_call, *args, **kwargs)

    async def _work_on() -> None:
        import os
        import subprocess
        from datetime import datetime
        from pathlib import Path

        import asana

        # Get settings for configuration
        settings = get_settings()

        # Initialize shutdown handler
        shutdown_handler = get_shutdown_handler(
            shutdown_timeout=settings.shutdown_timeout,
            subprocess_term_timeout=settings.subprocess_term_timeout
        )
        shutdown_handler.install_signal_handlers()

        # Register cleanup callbacks (order matters: mark tasks first, then orchestrator, then cleanup)
        shutdown_handler.register_cleanup_callback(mark_in_progress_tasks_interrupted_async)
        shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
        shutdown_handler.register_cleanup_callback(cleanup_db_connections)

        try:
            portfolio_gid = settings.asana_portfolio_gid

            # Mark as running (optional, for when full orchestrator is implemented)
            try:
                mark_orchestrator_running()
            except Exception as e:
                logger.warning("failed_to_mark_running", error=str(e))

            console.print(f"[bold]Analyzing {task_or_project} project...[/bold]")

            # Configure API client
            configuration = asana.Configuration()
            configuration.access_token = settings.asana_access_token
            api_client = asana.ApiClient(configuration)
            portfolios_api = asana.PortfoliosApi(api_client)
            projects_api = asana.ProjectsApi(api_client)
            tasks_api = asana.TasksApi(api_client)
            stories_api = asana.StoriesApi(api_client)
            users_api = asana.UsersApi(api_client)

            # Get projects from portfolio
            projects_generator = await fetch_with_retry(
                portfolios_api.get_items_for_portfolio, portfolio_gid, {"opt_fields": "name,gid"}
            )
            projects_list = list(projects_generator)

            # Find matching project
            project = None
            for proj in projects_list:
                if proj["name"].lower() == task_or_project.lower():
                    project = proj
                    break

            if not project:
                console.print(f"[red]Error: Project '{task_or_project}' not found in portfolio[/red]")
                sys.exit(1)

            console.print(f"✓ Found project: {project['name']} (GID: {project['gid']})\n")

            # Get project details
            project_details = await fetch_with_retry(
                projects_api.get_project, project["gid"], {"opt_fields": "name,notes"}
            )

            # Extract code path
            code_path = None
            if project_details.get("notes"):
                for line in project_details["notes"].split("\n"):
                    if line.startswith("Code Location:"):
                        code_path = line.split(":", 1)[1].strip()
                        code_path = os.path.expanduser(code_path)
                        break

            # Get all tasks
            console.print("Fetching all tasks...")
            tasks_generator = await fetch_with_retry(
                tasks_api.get_tasks_for_project,
                project["gid"],
                {"opt_fields": "name,notes,completed,assignee.name,gid,permalink_url"},
            )
            tasks_list = list(tasks_generator)

            # First, check for answered Question tasks (incomplete Question tasks that are now unassigned)
            # These need to be marked complete and moved to "Answered" section
            answered_questions = []
            for task in tasks_list:
                if (not task.get("completed") and
                    not task.get("assignee") and
                    task.get("name", "").startswith("Question:")):
                    answered_questions.append(task)

            if answered_questions:
                console.print(f"[cyan]Found {len(answered_questions)} answered Question task(s) to complete...[/cyan]")
                from aegis.asana.client import AsanaClient
                asana_client = AsanaClient(settings.asana_access_token)

                for question_task in answered_questions:
                    try:
                        console.print(f"  • Completing: {question_task['name']}")
                        await asana_client.complete_task_and_move_to_answered(
                            question_task["gid"],
                            project["gid"]
                        )
                        console.print("    [green]✓[/green] Marked complete and moved to Answered")
                    except Exception as e:
                        logger.warning(
                            "failed_to_complete_question",
                            task_gid=question_task["gid"],
                            error=str(e)
                        )
                        console.print(f"    [yellow]⚠[/yellow] Failed to complete: {e}")

                console.print()

            # Categorize tasks
            incomplete_unassigned = []
            for task in tasks_list:
                if not task.get("completed") and not task.get("assignee"):
                    # Skip Question tasks as they've been handled above
                    if not task.get("name", "").startswith("Question:"):
                        incomplete_unassigned.append(task)

            console.print(f"✓ Found {len(incomplete_unassigned)} incomplete unassigned tasks\n")

            if not incomplete_unassigned:
                console.print("[yellow]No unassigned tasks to work on![/yellow]")
                return

            # Analyze tasks for blockers (simple keyword detection)
            console.print("[bold]Assessing project state...[/bold]")

            blocked_tasks = []
            ready_tasks = []
            questions_needed = {}  # Changed to dict: question_type -> question_details

            # Check if question tasks already exist in project
            existing_questions = {}  # name -> gid mapping
            for task in tasks_list:
                if task.get("name", "").startswith("Question:"):
                    existing_questions[task["name"]] = task["gid"]

            for task in incomplete_unassigned:
                notes = task.get("notes", "").lower()

                # Check for blocker keywords
                is_blocked = False
                blocker_reason = None
                blocker_type = None

                if "dependencies:" in notes or "depends on:" in notes or "blocked by:" in notes:
                    is_blocked = True
                    blocker_reason = "Has explicit dependencies in description"
                    blocker_type = None  # Can't auto-create question for this
                elif "postgresql" in notes and "set up" in notes:
                    # Check if PostgreSQL is actually available
                    try:
                        import subprocess
                        result = subprocess.run(
                            ["docker", "ps", "--filter", "name=aegis-postgres", "--format", "{{.Names}}"],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if "aegis-postgres" not in result.stdout:
                            is_blocked = True
                            blocker_reason = "Requires PostgreSQL (container not running)"
                            blocker_type = "postgresql_setup"

                            # Only add question if it doesn't already exist
                            question_name = "Question: PostgreSQL Setup"
                            if blocker_type not in questions_needed and question_name not in existing_questions:
                                questions_needed[blocker_type] = {
                                    "question": "PostgreSQL Setup",
                                    "reason": "PostgreSQL database needs to be set up before proceeding",
                                    "blocked_task_gids": []  # Track which tasks are blocked by this
                                }

                            # Track this task as blocked by this question
                            if blocker_type in questions_needed:
                                questions_needed[blocker_type]["blocked_task_gids"].append(task["gid"])
                            elif question_name in existing_questions:
                                # Question already exists, we'll need to add dependency
                                if blocker_type not in questions_needed:
                                    questions_needed[blocker_type] = {
                                        "question": "PostgreSQL Setup",
                                        "task_gid": existing_questions[question_name],
                                        "blocked_task_gids": [task["gid"]]
                                    }
                                else:
                                    questions_needed[blocker_type]["blocked_task_gids"].append(task["gid"])
                    except Exception:
                        pass

                if is_blocked:
                    blocked_tasks.append({"task": task, "reason": blocker_reason, "blocker_type": blocker_type})
                else:
                    ready_tasks.append(task)

            # Report status
            if blocked_tasks:
                console.print(f"[yellow]⚠ Blocked tasks: {len(blocked_tasks)}[/yellow]")
                for item in blocked_tasks[:3]:  # Show first 3
                    console.print(f"  • {item['task']['name']}")
                    if item["reason"]:
                        console.print(f"    Reason: {item['reason']}")

            if questions_needed:
                console.print(f"\n[blue]? Questions to create: {len(questions_needed)}[/blue]")
                for q_details in questions_needed.values():
                    console.print(f"  • {q_details['question']}")

            console.print(f"\n[green]✓ Ready tasks: {len(ready_tasks)}[/green]")
            if ready_tasks:
                for task in ready_tasks[:5]:  # Show first 5
                    console.print(f"  • {task['name']}")

            if dry_run:
                console.print("\n[yellow]Dry run mode - no tasks executed[/yellow]")
                return

            # Fetch existing questions once for use in both question creation and task execution
            console.print("\n[dim]Fetching existing question tasks...[/dim]")
            current_tasks = await asyncio.to_thread(
                tasks_api.get_tasks_for_project,
                project["gid"],
                {"opt_fields": "name,gid,completed"}
            )
            existing_questions_now = {}
            for task in current_tasks:
                task_dict = task if isinstance(task, dict) else task.to_dict()
                if task_dict.get("name", "").startswith("Question:") and not task_dict.get("completed", False):
                    existing_questions_now[task_dict["name"]] = task_dict["gid"]
            console.print(f"[dim]Found {len(existing_questions_now)} existing question(s)[/dim]")

            # Create question tasks if needed
            if questions_needed:
                console.print("\n[bold]Creating question tasks...[/bold]")
                me = await asyncio.to_thread(users_api.get_user, "me", {})
                me_gid = me["gid"]

                for _q_type, q_details in questions_needed.items():
                    # Skip if question already exists (has task_gid)
                    if "task_gid" in q_details:
                        continue

                    # Double-check that question doesn't exist right before creating
                    question_name = f"Question: {q_details['question']}"
                    if question_name in existing_questions_now:
                        console.print(f"  ⊙ Question already exists: {question_name}")
                        q_details["task_gid"] = existing_questions_now[question_name]
                        continue

                    question_text = f"""**From**: Claude (Aegis Autonomous Agent)
**Context**: Working on project assessment
**Blocker**: {q_details.get('reason', 'Setup required')}

## Question: {q_details['question']}

This task requires setup that isn't complete yet. Please choose how to proceed:

## Options

1. **Docker Compose** (Recommended)
   - Run: `docker compose up -d` in project directory
   - Pros: Isolated, easy to reset, includes Redis
   - Cons: Requires Docker Desktop running

2. **Local PostgreSQL**
   - Install via Homebrew: `brew install postgresql@16`
   - Pros: Always available, better performance
   - Cons: System-wide installation

## Action Needed

Reply with your choice (1 or 2) and I'll proceed accordingly.
"""

                    question_task_data = {
                        "data": {
                            "name": question_name,
                            "notes": question_text,
                            "projects": [project["gid"]],
                            "assignee": me_gid,
                        }
                    }

                    result = await asyncio.to_thread(
                        tasks_api.create_task,
                        question_task_data,
                        {"opt_fields": "name,gid"}
                    )
                    console.print(f"  ✓ Created: {result['name']} (GID: {result['gid']})")

                    # Store question task GID for dependency tracking
                    q_details["task_gid"] = result["gid"]
                    # Also add to existing_questions_now to prevent duplicates in same run
                    existing_questions_now[question_name] = result["gid"]

                # Now create dependencies for all blocked tasks
                console.print("\n[bold]Creating Asana dependencies...[/bold]")
                for _q_type, q_details in questions_needed.items():
                    if "task_gid" in q_details and "blocked_task_gids" in q_details:
                        question_gid = q_details["task_gid"]
                        for blocked_task_gid in q_details["blocked_task_gids"]:
                            try:
                                # Add dependency: blocked_task depends on question_task
                                await asyncio.to_thread(
                                    tasks_api.add_dependencies_for_task,
                                    blocked_task_gid,
                                    {"body": {"data": {"dependencies": [question_gid]}}}
                                )
                                console.print(f"  ✓ Made task {blocked_task_gid[:8]}... depend on question")
                            except Exception as e:
                                logger.warning("failed_to_create_dependency",
                                             task_gid=blocked_task_gid,
                                             question_gid=question_gid,
                                             error=str(e))

            # Review recently completed tasks in Implemented section and move failures to Failed
            console.print("\n[bold]Reviewing recently completed tasks...[/bold]")
            try:
                from datetime import datetime, timedelta

                from aegis.asana.client import AsanaClient
                asana_client = AsanaClient(settings.asana_access_token)

                # Get sections
                sections = await asana_client.get_sections(project["gid"])
                section_map = {s.name: s.gid for s in sections}

                # Check if Implemented and Failed sections exist
                if "Implemented" in section_map and "Failed" in section_map:
                    # Get tasks from Implemented section
                    implemented_tasks = await asana_client.get_tasks_for_section(section_map["Implemented"])

                    # Filter for recently completed tasks (last 24 hours)
                    cutoff_time = datetime.utcnow() - timedelta(days=1)
                    tasks_to_review = []

                    for task in implemented_tasks:
                        if task.completed and task.completed_at:
                            # Parse ISO timestamp
                            completed_time = datetime.fromisoformat(task.completed_at.replace('Z', '+00:00'))
                            if completed_time > cutoff_time:
                                tasks_to_review.append(task)

                    if tasks_to_review:
                        console.print(f"  Found {len(tasks_to_review)} task(s) completed in last 24h")

                        # Check each task's comments for failure indicators
                        failed_tasks_to_move = []
                        for task in tasks_to_review:
                            try:
                                comments = await asana_client.get_comments(task.gid)

                                # Look for failure indicators in most recent comments
                                for comment in reversed(comments[-5:]):  # Check last 5 comments
                                    comment_text = comment.text.lower()
                                    # Check for failure/error/timeout indicators
                                    if any(indicator in comment_text for indicator in [
                                        "⚠️", "⏱️", "✗",
                                        "completed with errors",
                                        "exit code",
                                        "timed out",
                                        "timeout after",
                                        "failed",
                                        "error:"
                                    ]):
                                        failed_tasks_to_move.append(task)
                                        console.print(f"  • Found failed task: {task.name}")
                                        break
                            except Exception as e:
                                logger.warning("failed_to_check_task_comments", task_gid=task.gid, error=str(e))

                        # Move failed tasks to Failed section and reopen them
                        if failed_tasks_to_move:
                            console.print(f"\n  [yellow]Moving {len(failed_tasks_to_move)} failed task(s) to Failed section...[/yellow]")
                            for task in failed_tasks_to_move:
                                try:
                                    # Reopen the task
                                    await asyncio.to_thread(
                                        tasks_api.update_task,
                                        task.gid,
                                        {"data": {"completed": False}}
                                    )

                                    # Move to Failed section
                                    await asana_client.move_task_to_section(
                                        task.gid,
                                        project["gid"],
                                        section_map["Failed"]
                                    )

                                    console.print(f"    ✓ Moved and reopened: {task.name}")
                                except Exception as e:
                                    logger.warning("failed_to_move_failed_task", task_gid=task.gid, error=str(e))
                                    console.print(f"    ✗ Failed to move: {task.name}: {e}")
                        else:
                            console.print("  [green]✓ No failures found in recent completions[/green]")
                    else:
                        console.print("  [dim]No tasks completed in last 24h[/dim]")
                else:
                    console.print("  [yellow]⚠ Implemented or Failed section not found - skipping review[/yellow]")

            except Exception as e:
                logger.error("review_failed_tasks_error", error=str(e))
                console.print(f"  [yellow]⚠ Error reviewing completed tasks: {e}[/yellow]")

            # Execute ready tasks (up to max_tasks)
            if ready_tasks:
                tasks_to_execute = ready_tasks[:max_tasks]
                console.print(f"\n[bold]Executing {len(tasks_to_execute)} ready task(s)...[/bold]\n")

                working_dir = code_path if code_path and os.path.isdir(code_path) else None

                logs_dir = Path.cwd() / "logs"
                logs_dir.mkdir(exist_ok=True)
                log_file = logs_dir / f"{task_or_project.lower()}.log"

                completed_count = 0
                failed_count = 0

                for idx, task in enumerate(tasks_to_execute, 1):
                    # Check for shutdown request before starting new task
                    if shutdown_handler.shutdown_requested:
                        console.print(f"\n[yellow]⚠ Shutdown requested, stopping after {completed_count} tasks[/yellow]")
                        logger.info("shutdown_requested_stopping_execution", completed=completed_count)
                        break

                    console.print(f"[bold][{idx}/{len(tasks_to_execute)}] {task['name']}[/bold]")
                    console.print(f"  Working directory: {working_dir or 'current directory'}")

                    # Format task context
                    task_context = f"""Task: {task['name']}
Task GID: {task['gid']}
Project: {project['name']}
Project GID: {project['gid']}"""

                    if code_path:
                        task_context += f"\nCode Location: {code_path}"

                    # Add existing questions to context to prevent duplicates
                    if existing_questions_now:
                        task_context += "\n\nExisting Question Tasks (DO NOT CREATE DUPLICATES):\n" + "\n".join(f"  - {q}" for q in existing_questions_now)

                    if task.get("notes"):
                        task_context += f"\n\nTask Description:\n{task['notes']}"

                    task_context += f"""

IMPORTANT: You are running in HEADLESS mode.

- Do not ask the user questions or wait for input
- If you need clarification, CHECK THE "Existing Question Tasks" LIST ABOVE FIRST
- Only create a NEW Question task if it doesn't already exist (exact name match required)
- Question task format: "Question: [specific question]" (must start with "Question: ")
- Use the Asana API to create question tasks and add them as dependencies to blocked tasks

When you have completed this task, you must:

1. Post a comment to the Asana task with a summary of what you accomplished
2. Mark the task as complete in Asana
3. Move the task to the "Implemented" section

Use this Python helper:
```bash
python -m aegis.agent_helpers {task['gid']} {project['gid']} "YOUR_SUMMARY_HERE"
```

After completing these steps, EXIT. Do not wait for further input."""

                    timestamp = datetime.now().isoformat()

                    try:
                        # Run in terminal mode if enabled
                        if terminal:
                            console.print("  [cyan]Launching Claude Code in new Hyper terminal...[/cyan]")
                            launch_in_hyper_terminal(
                                ["claude", "--dangerously-skip-permissions", task_context],
                                cwd=working_dir
                            )
                            console.print("  [dim]Task running in terminal - check Hyper window for progress[/dim]")

                            # For terminal mode, we can't easily track completion or get output
                            # So we'll just mark it as completed in the log and continue
                            with open(log_file, "a") as f:
                                f.write(f"\n{'=' * 80}\n")
                                f.write(f"[{timestamp}] Task: {task['name']}\n")
                                f.write("Status: LAUNCHED IN TERMINAL\n")
                                f.write(f"{'=' * 80}\n\n")

                            completed_count += 1
                            console.print("  [green]✓ Launched successfully[/green]\n")
                            continue

                        # Run claude with output capture using Popen for tracking
                        process = subprocess.Popen(
                            ["claude", "--dangerously-skip-permissions", task_context],
                            cwd=working_dir,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            text=True,
                        )

                        # Track the subprocess for graceful shutdown
                        shutdown_handler.track_subprocess(process)

                        try:
                            # Wait for completion with timeout
                            stdout, stderr = process.communicate(timeout=timeout)
                        except subprocess.TimeoutExpired:
                            console.print(f"  [red]✗ Task execution timed out after {timeout} seconds[/red]")
                            console.print("  [yellow]Suggestions:[/yellow]")
                            console.print(f"    • Increase timeout: --timeout {timeout * 2}")
                            console.print("    • Break task into smaller sub-tasks")
                            console.print(f"    • Check log file: {log_file}")

                            # Kill the process and get any partial output
                            process.kill()
                            stdout, stderr = process.communicate()

                            # Log the timeout
                            with open(log_file, "a") as f:
                                f.write(f"\n{'='*80}\n[{timestamp}] Task: {task['name']}\n")
                                f.write(f"STATUS: TIMEOUT after {timeout}s\n")
                                if stdout:
                                    f.write(f"\nPartial STDOUT:\n{stdout}\n")
                                if stderr:
                                    f.write(f"\nSTDERR:\n{stderr}\n")
                                f.write(f"{'='*80}\n\n")

                            # Post timeout notification to Asana
                            timeout_comment = f"""⏱️ Task execution timed out after {timeout} seconds

**Timestamp**: {timestamp}

**Partial output**:
```
{stdout[:30000] if stdout else '(No output captured before timeout)'}
```

**Suggestions**:
- Increase timeout: `--timeout {timeout * 2}`
- Break task into smaller sub-tasks
- Review partial output above for progress

**Log file**: `{log_file}`
"""
                            comment_data = {"data": {"text": timeout_comment}}
                            try:
                                await post_asana_comment(stories_api, comment_data, task["gid"])
                            except Exception as e:
                                console.print(f"  [yellow]Warning: Failed to post timeout comment: {e}[/yellow]")

                            # Move task to Failed section
                            try:
                                from aegis.asana.client import AsanaClient
                                asana_client = AsanaClient(config.asana_access_token)

                                # Get sections
                                sections = await asana_client.get_sections(project["gid"])
                                section_map = {s.name: s.gid for s in sections}

                                if "Failed" in section_map:
                                    await asana_client.move_task_to_section(
                                        task["gid"],
                                        project["gid"],
                                        section_map["Failed"]
                                    )
                                    console.print("  [yellow]→ Moved to Failed section[/yellow]")
                            except Exception as e:
                                logger.warning("failed_to_move_task", task_gid=task["gid"], error=str(e))
                                console.print(f"  [yellow]⚠ Could not move to Failed: {e}[/yellow]")

                            # Untrack and continue to next task
                            shutdown_handler.untrack_subprocess(process)
                            failed_count += 1
                            console.print("  [yellow]Skipping to next task...[/yellow]\n")
                            continue

                        finally:
                            # Always untrack when done (whether success or failure)
                            shutdown_handler.untrack_subprocess(process)

                        output = stdout
                        if stderr:
                            output += f"\n\nSTDERR:\n{stderr}"

                        # Create result object similar to subprocess.run()
                        class Result:
                            def __init__(self, returncode, stdout, stderr):
                                self.returncode = returncode
                                self.stdout = stdout
                                self.stderr = stderr

                        result = Result(process.returncode, stdout, stderr)

                        # Write to log
                        log_header = f"\n{'='*80}\n[{timestamp}] Task: {task['name']}\n{'='*80}\n\n"
                        with open(log_file, "a") as f:
                            f.write(log_header)
                            f.write(output)
                            f.write(f"\n\nExit code: {result.returncode}\n")

                        # Post comment to Asana
                        status_emoji = "✓" if result.returncode == 0 else "⚠️"
                        status_text = "completed" if result.returncode == 0 else f"completed with errors (exit code {result.returncode})"

                        comment_text = f"""{status_emoji} Task {status_text} via Aegis (work-on mode)

**Timestamp**: {timestamp}

**Output**:
```
{output[:60000] if output else '(No output captured)'}
```

**Log file**: `{log_file}`
"""

                        comment_data = {"data": {"text": comment_text}}
                        await post_asana_comment(stories_api, comment_data, task["gid"])

                        if result.returncode == 0:
                            # Mark task as complete and move to appropriate section
                            try:
                                from aegis.asana.client import AsanaClient
                                asana_client = AsanaClient(config.asana_access_token)

                                # Check if this is a question task
                                is_question = task['name'].lower().startswith("question:")

                                if is_question:
                                    # Move to Answered section
                                    await asana_client.complete_task_and_move_to_answered(
                                        task["gid"],
                                        project["gid"]
                                    )
                                    console.print("  [green]✓ Completed and moved to Answered[/green]\n")
                                else:
                                    # Move to Implemented section
                                    await asana_client.complete_task_and_move_to_implemented(
                                        task["gid"],
                                        project["gid"]
                                    )
                                    console.print("  [green]✓ Completed and moved to Implemented[/green]\n")
                                completed_count += 1
                            except Exception as e:
                                logger.warning("failed_to_complete_task", task_gid=task["gid"], error=str(e))
                                console.print(f"  [yellow]⚠ Completed but failed to move: {e}[/yellow]\n")
                                completed_count += 1
                        else:
                            # Task failed - move to Failed section but don't mark complete
                            console.print(f"  [red]✗ Task failed (exit code: {result.returncode})[/red]")
                            try:
                                from aegis.asana.client import AsanaClient
                                asana_client = AsanaClient(config.asana_access_token)

                                # Get sections
                                sections = await asana_client.get_sections(project["gid"])
                                section_map = {s.name: s.gid for s in sections}

                                if "Failed" in section_map:
                                    await asana_client.move_task_to_section(
                                        task["gid"],
                                        project["gid"],
                                        section_map["Failed"]
                                    )
                                    console.print("  [yellow]→ Moved to Failed section[/yellow]\n")
                                else:
                                    console.print("  [yellow]⚠ 'Failed' section not found - task left in current section[/yellow]\n")
                            except Exception as e:
                                logger.warning("failed_to_move_task", task_gid=task["gid"], error=str(e))
                                console.print(f"  [yellow]⚠ Could not move to Failed: {e}[/yellow]\n")
                            failed_count += 1

                    except subprocess.TimeoutExpired:
                        console.print("  [red]✗ Timeout (5 minutes)[/red]\n")
                        failed_count += 1
                    except Exception as e:
                        console.print(f"  [red]✗ Error: {e}[/red]\n")
                        failed_count += 1

                # Summary
                console.print("=" * 60)
                console.print("[bold]Session Summary[/bold]")
                console.print(f"  ✓ Completed: {completed_count} tasks")
                if failed_count:
                    console.print(f"  ⚠ Failed/Warnings: {failed_count} tasks")
                if blocked_tasks:
                    console.print(f"  ⚠ Blocked: {len(blocked_tasks)} tasks")
                if questions_needed:
                    console.print(f"  ? Questions: {len(questions_needed)} created")
                console.print(f"\nLog: {log_file}")
                console.print("=" * 60)

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()
        finally:
            # Always run shutdown sequence
            try:
                await shutdown_handler.shutdown()
                console.print("\n[dim]Shutdown complete[/dim]")
            except Exception as e:
                logger.error("shutdown_failed", error=str(e), exc_info=True)
                console.print(f"[red]Warning: Shutdown encountered errors: {e}[/red]")

    try:
        asyncio.run(_work_on())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)  # Standard exit code for SIGINT


@main.command()
@click.argument("task_or_project")
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
def organize(task_or_project: str, use_console: bool) -> None:
    """Apply project structure template to organize sections.

    Use "all" to organize all projects in the portfolio.
    """
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    async def _organize() -> None:
        from aegis.asana.client import AsanaClient

        try:
            settings = get_settings()
            portfolio_gid = settings.asana_portfolio_gid

            # Standard sections for all projects
            STANDARD_SECTIONS = [
                "Waiting for Response",
                "Ready to Implement",
                "In Progress",
                "Implemented",
                "Failed",
                "Answered",
                "Ideas",
            ]

            # Initialize Asana client
            asana_client = AsanaClient(settings.asana_access_token)

            # Get projects from portfolio
            import asana
            configuration = asana.Configuration()
            configuration.access_token = settings.asana_access_token
            api_client = asana.ApiClient(configuration)
            portfolios_api = asana.PortfoliosApi(api_client)

            projects_generator = await asyncio.to_thread(
                portfolios_api.get_items_for_portfolio,
                portfolio_gid,
                {"opt_fields": "name,gid"}
            )
            projects_list = list(projects_generator)

            # Determine which projects to organize
            if task_or_project.lower() == "all":
                projects_to_organize = projects_list
                console.print(f"[bold]Organizing all {len(projects_to_organize)} projects...[/bold]\n")
            else:
                # Find matching project
                project = None
                for proj in projects_list:
                    if proj["name"].lower() == task_or_project.lower():
                        project = proj
                        break

                if not project:
                    console.print(f"[red]Error: Project '{task_or_project}' not found in portfolio[/red]")
                    console.print("\nAvailable projects:")
                    for proj in projects_list:
                        console.print(f"  - {proj['name']}")
                    sys.exit(1)

                projects_to_organize = [project]
                console.print(f"[bold]Organizing project: {project['name']}[/bold]\n")

            # Organize each project
            for project in projects_to_organize:
                console.print(f"Processing: {project['name']}")

                # Ensure project has standard sections
                section_map = await asana_client.ensure_project_sections(
                    project["gid"],
                    STANDARD_SECTIONS
                )

                console.print(f"  [green]✓[/green] Ensured {len(section_map)} sections")
                for section_name in STANDARD_SECTIONS:
                    if section_name in section_map:
                        console.print(f"    - {section_name}")

                console.print()

            console.print("[bold green]Organization complete![/bold green]")

        except Exception as e:
            console.print(f"[red]Error organizing projects: {e}[/red]")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    asyncio.run(_organize())


@main.command()
@click.argument("task_or_project")
@click.option("--target", default=5, help="Target number of tasks in 'Ready to Implement' (default: 5)")
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
@click.option("--no-consolidate", is_flag=True, help="Skip task consolidation (only check task count)")
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
@click.option("--timeout", default=600, help="Timeout in seconds for Claude CLI calls (default: 600)")
@click.option("--max-tasks", default=20, help="Maximum number of tasks to analyze at once (default: 20)")
def plan(task_or_project: str, target: int, dry_run: bool, no_consolidate: bool, use_console: bool, timeout: int, max_tasks: int) -> None:
    """Review tasks and ensure target number of tasks are in 'Ready to Implement' section.

    This command:
    - Reviews current task list
    - Ensures target number of tasks are in "Ready to Implement" section
    - Pulls tasks from other sections (prioritizes "Ideas" and unassigned sections)
    - Uses Claude to consolidate/cleanup tasks as needed (unless --no-consolidate)
    """
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    async def _plan() -> None:
        import os
        import subprocess

        from aegis.asana.client import AsanaClient

        try:
            settings = get_settings()
            portfolio_gid = settings.asana_portfolio_gid

            # Initialize Asana client
            asana_client = AsanaClient(settings.asana_access_token)

            # Get projects from portfolio
            import asana
            configuration = asana.Configuration()
            configuration.access_token = settings.asana_access_token
            api_client = asana.ApiClient(configuration)
            portfolios_api = asana.PortfoliosApi(api_client)

            projects_generator = await asyncio.to_thread(
                portfolios_api.get_items_for_portfolio,
                portfolio_gid,
                {"opt_fields": "name,gid"}
            )
            projects_list = list(projects_generator)

            # Find matching project
            project = None
            for proj in projects_list:
                if proj["name"].lower() == task_or_project.lower():
                    project = proj
                    break

            if not project:
                console.print(f"[red]Error: Project '{task_or_project}' not found in portfolio[/red]")
                console.print("\nAvailable projects:")
                for proj in projects_list:
                    console.print(f"  - {proj['name']}")
                sys.exit(1)

            console.print(f"[bold]Planning tasks for: {project['name']}[/bold]\n")
            console.print(f"Target: {target} tasks in 'Ready to Implement'\n")

            # Get sections
            sections = await asana_client.get_sections(project["gid"])
            section_map = {s.name: s.gid for s in sections}

            # Check for required section
            if "Ready to Implement" not in section_map:
                console.print("[red]Error: 'Ready to Implement' section not found[/red]")
                console.print("Run 'aegis organize' first to set up project sections")
                sys.exit(1)

            # Get tasks for each section
            console.print("[bold]Analyzing sections...[/bold]")
            section_tasks = {}
            for section_name, section_gid in section_map.items():
                tasks = await asana_client.get_tasks_for_section(section_gid)
                # Filter for incomplete tasks only
                incomplete_tasks = [t for t in tasks if not t.completed]
                section_tasks[section_name] = incomplete_tasks
                console.print(f"  {section_name}: {len(incomplete_tasks)} incomplete tasks")

            console.print()

            # Count tasks in "Ready to Implement"
            ready_tasks = section_tasks.get("Ready to Implement", [])
            current_count = len(ready_tasks)

            console.print(f"[bold]Current state:[/bold] {current_count} tasks in 'Ready to Implement'")

            if current_count >= target:
                console.print(f"[green]✓ Already have {current_count} tasks ready (target: {target})[/green]")

                # Skip consolidation if flag is set
                if no_consolidate:
                    console.print("\n[dim]Skipping consolidation (--no-consolidate flag set)[/dim]")
                    return

                # Ask Claude to review and consolidate if needed
                console.print("\n[bold]Asking Claude to review and consolidate tasks...[/bold]")

                # Limit tasks to analyze if there are too many
                tasks_to_analyze = ready_tasks[:max_tasks]
                if len(ready_tasks) > max_tasks:
                    console.print(f"[yellow]Note: Limiting analysis to first {max_tasks} of {current_count} tasks[/yellow]")
                    console.print(f"[dim]Use --max-tasks {current_count} to analyze all tasks[/dim]")

                # Build context for Claude
                task_list = "\n".join([f"- {t.name}\n  GID: {t.gid}\n  Notes: {t.notes[:100] if t.notes else '(none)'}..."
                                      for t in tasks_to_analyze])

                claude_prompt = f"""You are running in HEADLESS mode. Do not ask questions or wait for user input.

Project: {project['name']}
Project GID: {project["gid"]}

Current tasks in "Ready to Implement" ({len(tasks_to_analyze)} tasks being analyzed):
{task_list}

Your task: CAREFULLY review each task and identify issues that would block implementation.

STEP 1 - ANALYZE EACH TASK THOROUGHLY:
For each task, think carefully about:
- Is the task description clear and specific enough to implement?
- Are there multiple ways to interpret this task?
- What technical decisions need to be made (e.g., which library, which approach, what UI pattern)?
- Are there missing requirements or acceptance criteria?
- Is this task actually 2-3 separate tasks that should be split?
- Are there obvious duplicates with other tasks?
- Does this task have dependencies that aren't explicitly stated?

STEP 2 - CREATE QUESTION TASKS FOR AMBIGUITIES:
For any task that has unclear requirements or needs clarification:
1. Create a NEW question task in Asana with title: "Question: [specific question about the task]"
2. In the question task's description, include:
   - Which task it relates to (include the task name and GID)
   - What specifically needs clarification
   - Why this clarification is needed for implementation
   - Options or context to help the user answer
3. Add the question task as a DEPENDENCY to the original task (the original task is blocked by the question)
4. Move the original task to "Waiting for Response" section
5. Post a comment on the original task: "Blocked: needs clarification - see [Question Task GID]"

STEP 3 - CONSOLIDATE DUPLICATES:
For duplicate or very similar tasks:
- Update one task to include all information from the duplicates
- Delete or mark duplicate tasks as complete
- Post a comment explaining the consolidation

STEP 4 - PROVIDE SUMMARY:
List all actions taken:
- Question tasks created (with titles and GIDs)
- Dependencies added (which tasks are blocked by which questions)
- Tasks consolidated (which were merged into which)
- Tasks moved to "Waiting for Response"

IMPORTANT: You have access to the Asana API. Use it to:
- Create question tasks in the same project
- Add dependencies between tasks (use add_dependencies_for_task)
- Update task names and descriptions
- Move tasks to appropriate sections (use move_task_to_section)
- Delete duplicate tasks
- Post comments to explain your changes

Be THOROUGH - it's better to create a question task than to have an implementation fail due to unclear requirements. Think step-by-step for each task.

Begin your careful analysis now."""

                if dry_run:
                    console.print("[yellow]Dry run mode - would call Claude with:[/yellow]")
                    console.print(f"[dim]{claude_prompt[:500]}...[/dim]")
                else:
                    # Get project code path for context
                    import asana
                    configuration = asana.Configuration()
                    configuration.access_token = settings.asana_access_token
                    api_client = asana.ApiClient(configuration)
                    projects_api = asana.ProjectsApi(api_client)

                    project_details = await asyncio.to_thread(
                        projects_api.get_project,
                        project["gid"],
                        {"opt_fields": "name,notes"}
                    )

                    # Extract code path from notes
                    code_path = None
                    if project_details.get("notes"):
                        for line in project_details["notes"].split("\n"):
                            if line.startswith("Code Location:"):
                                code_path = line.split(":", 1)[1].strip()
                                code_path = os.path.expanduser(code_path)
                                break

                    working_dir = code_path if code_path and os.path.isdir(code_path) else None

                    # Run claude CLI for analysis and consolidation
                    console.print(f"[dim]Running consolidation in headless mode (timeout: {timeout}s)...[/dim]\n")

                    try:
                        result = subprocess.run(
                            ["claude", "--dangerously-skip-permissions", claude_prompt],
                            capture_output=True,
                            text=True,
                            timeout=timeout,
                            cwd=working_dir
                        )

                        console.print("\n[bold cyan]Consolidation Results:[/bold cyan]")
                        console.print(result.stdout)

                        if result.returncode != 0:
                            console.print(f"\n[yellow]Warning: Claude exited with code {result.returncode}[/yellow]")
                            if result.stderr:
                                console.print(f"[dim]STDERR: {result.stderr[:500]}[/dim]")

                    except subprocess.TimeoutExpired:
                        console.print(f"\n[red]Error: Claude timed out after {timeout} seconds[/red]")
                        console.print("[yellow]Suggestions:[/yellow]")
                        console.print(f"  • Increase timeout: --timeout {timeout * 2}")
                        console.print(f"  • Reduce task count: --max-tasks {max(5, max_tasks // 2)}")
                        console.print("  • Skip consolidation: --no-consolidate")
                        sys.exit(1)

                return

            # Need to move tasks to Ready to Implement
            needed = target - current_count
            console.print(f"[yellow]Need to move {needed} tasks to 'Ready to Implement'[/yellow]\n")

            # Prioritize sections to pull from (in order)
            source_sections = ["Ideas", "Waiting for Response", "In Progress"]

            # Collect candidate tasks
            candidates = []
            for section_name in source_sections:
                if section_name in section_tasks:
                    for task in section_tasks[section_name]:
                        # Skip assigned tasks in "In Progress"
                        if section_name == "In Progress" and task.assignee:
                            continue
                        candidates.append((section_name, task))

            if len(candidates) < needed:
                console.print(f"[yellow]Warning: Only found {len(candidates)} candidate tasks (need {needed})[/yellow]")

            # Build context for Claude to decide which tasks to move
            console.print("[bold]Asking Claude to select and prioritize tasks...[/bold]\n")

            candidates_text = "\n".join([
                f"- [{source}] {task.name}\n  GID: {task.gid}\n  Notes: {task.notes[:200] if task.notes else '(none)'}..."
                for source, task in candidates[:20]  # Limit to first 20 candidates
            ])

            current_ready_text = "\n".join([
                f"- {task.name}\n  GID: {task.gid}\n  Notes: {task.notes[:100] if task.notes else '(none)'}..."
                for task in ready_tasks
            ])

            claude_prompt = f"""You are running in HEADLESS mode. Do not ask questions or wait for user input.

You are helping prioritize tasks for a project. Select {needed} tasks from the candidate list to move to "Ready to Implement".

Project: {project['name']}
Project GID: {project["gid"]}
Target: Move {needed} tasks to "Ready to Implement"

Currently in "Ready to Implement" ({current_count} tasks):
{current_ready_text if current_ready_text else "(empty)"}

Candidate tasks to consider:
{candidates_text}

INSTRUCTIONS:

STEP 1 - ANALYZE EACH CANDIDATE CAREFULLY:
For each candidate task, consider:
- Is the task description clear and actionable?
- Are the requirements well-defined?
- Are there ambiguities that would block implementation?
- Does it have implied dependencies on other work?
- What technical choices or architectural decisions are needed?

STEP 2 - CREATE QUESTION TASKS FOR UNCLEAR CANDIDATES:
If a candidate task is unclear or ambiguous:
- CREATE a question task in Asana with title: "Question: [specific question]"
- Add it as a DEPENDENCY to the unclear task (the original task is blocked by the question)
- Move the original task to "Waiting for Response"
- Do NOT include that task in your selection below

STEP 3 - SELECT READY TASKS:
From the remaining clear, well-defined candidates:
1. Select the {needed} most important tasks
2. Prioritize tasks that:
   - Have clear requirements and acceptance criteria
   - Don't duplicate existing ready tasks
   - Provide high value or unblock other work
   - Don't require architectural decisions that haven't been made yet

STEP 4 - RESPOND WITH SELECTION:
Respond with ONLY a JSON array of task GIDs in priority order (highest priority first):
["gid1", "gid2", "gid3", ...]

Do not include any other text - just the JSON array.

IMPORTANT: Be selective - only include tasks that are truly ready to implement. If fewer than {needed} tasks are actually ready (due to ambiguities), that's fine - create question tasks for the unclear ones and return a shorter array."""

            if dry_run:
                console.print("[yellow]Dry run mode - would move these tasks:[/yellow]")
                for source, task in candidates[:needed]:
                    console.print(f"  [{source}] → Ready to Implement: {task.name}")
                console.print("\n[dim]Claude prompt (preview):[/dim]")
                console.print(f"[dim]{claude_prompt[:500]}...[/dim]")
                return

            # Call Claude to select tasks
            console.print(f"[dim]Consulting Claude for task selection (timeout: {timeout // 2}s)...[/dim]\n")

            try:
                result = subprocess.run(
                    ["claude", "--dangerously-skip-permissions", claude_prompt],
                    capture_output=True,
                    text=True,
                    timeout=timeout // 2  # Use half timeout for task selection (simpler task)
                )

                # Parse Claude's response
                import json
                import re

                output = result.stdout.strip()
                # Try to extract JSON array from response
                json_match = re.search(r'\[[\s\S]*\]', output)

            except subprocess.TimeoutExpired:
                console.print(f"\n[red]Error: Claude timed out after {timeout // 2} seconds[/red]")
                console.print("[yellow]Suggestions:[/yellow]")
                console.print(f"  • Increase timeout: --timeout {timeout * 2}")
                console.print("  • This usually indicates a complex decision - try reviewing tasks manually")
                sys.exit(1)

            if json_match:
                try:
                    selected_gids = json.loads(json_match.group(0))
                    console.print(f"[green]✓ Claude selected {len(selected_gids)} tasks[/green]\n")

                    # Move the selected tasks
                    tasks_by_gid = {task.gid: (source, task) for source, task in candidates}
                    moved_count = 0

                    for gid in selected_gids[:needed]:  # Limit to needed count
                        if gid in tasks_by_gid:
                            source, task = tasks_by_gid[gid]
                            console.print(f"  Moving: {task.name}")
                            console.print(f"    From: {source}")

                            await asana_client.move_task_to_section(
                                task.gid,
                                project["gid"],
                                section_map["Ready to Implement"]
                            )
                            moved_count += 1
                            console.print("    [green]✓ Moved to Ready to Implement[/green]\n")

                    console.print(f"[bold green]✓ Successfully moved {moved_count} tasks![/bold green]")
                    console.print(f"'Ready to Implement' now has {current_count + moved_count} tasks")

                except json.JSONDecodeError as e:
                    console.print(f"[red]Error parsing Claude's response as JSON: {e}[/red]")
                    console.print(f"Response: {output[:500]}")

                    # Fallback: move first N candidates
                    console.print("\n[yellow]Falling back to automatic selection...[/yellow]")
                    for source, task in candidates[:needed]:
                        console.print(f"  Moving: {task.name} (from {source})")
                        await asana_client.move_task_to_section(
                            task.gid,
                            project["gid"],
                            section_map["Ready to Implement"]
                        )
                    console.print(f"[green]✓ Moved {needed} tasks[/green]")
            else:
                console.print("[yellow]Could not parse Claude's response, using automatic selection[/yellow]")
                console.print(f"[dim]Response: {output[:200]}...[/dim]\n")

                # Fallback: move first N candidates
                for source, task in candidates[:needed]:
                    console.print(f"  Moving: {task.name} (from {source})")
                    await asana_client.move_task_to_section(
                        task.gid,
                        project["gid"],
                        section_map["Ready to Implement"]
                    )
                console.print(f"[green]✓ Moved {needed} tasks[/green]")

        except Exception as e:
            console.print(f"[red]Error planning project: {e}[/red]")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    asyncio.run(_plan())


@main.command()
@click.option("--name", default="Agents", help="Name of the Agents project (default: Agents)")
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
def create_agents_project(name: str, use_console: bool) -> None:
    """Create the Agents project in the portfolio.

    This project will contain agent definitions where:
    - Each task represents an agent
    - Task name is the agent's name
    - Task notes contain the agent's prompt/instructions
    """
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    async def _create_agents_project() -> None:
        from aegis.asana.client import AsanaClient

        try:
            settings = get_settings()
            asana_client = AsanaClient(settings.asana_access_token)

            console.print(f"[bold]Creating '{name}' project...[/bold]\n")

            # Create the project
            project = await asana_client.create_project(
                workspace_gid=settings.asana_workspace_gid,
                name=name,
                notes="Agent definitions for team-mate collaboration.\n\n"
                      "Each task in this project represents an agent:\n"
                      "- Task name = agent name\n"
                      "- Task notes = agent prompt/instructions\n\n"
                      "When an agent is @-mentioned in a task or comment, "
                      "it will respond based on its prompt.",
                public=True,
                team_gid=settings.asana_team_gid,
            )

            console.print(f"[green]✓ Created project: {project.name} (GID: {project.gid})[/green]\n")

            # Add project to portfolio
            console.print("Adding project to portfolio...")
            await asana_client.add_project_to_portfolio(
                portfolio_gid=settings.asana_portfolio_gid,
                project_gid=project.gid,
            )
            console.print("[green]✓ Added to portfolio[/green]\n")

            # Set up standard sections
            console.print("Setting up sections...")
            section_names = [
                "Active Agents",
                "Inactive Agents",
            ]

            section_map = await asana_client.ensure_project_sections(
                project.gid, section_names
            )
            console.print(f"[green]✓ Created {len(section_map)} sections[/green]\n")

            console.print("[bold green]✓ Agents project created successfully![/bold green]")
            console.print(f"\nProject URL: https://app.asana.com/0/{project.gid}")
            console.print("\nNext steps:")
            console.print(f"1. Create tasks in '{name}' to define your agents")
            console.print("2. Set task name = agent name")
            console.print("3. Set task notes = agent prompt")
            console.print("4. Use '@agent-name' to mention agents in tasks/comments")

        except Exception as e:
            console.print(f"[red]Error creating Agents project: {e}[/red]")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    asyncio.run(_create_agents_project())


@main.command()
@click.argument("project_name")
@click.option("--agents-project", default="Agents", help="Name of the Agents project (default: Agents)")
@click.option("--poll-interval", default=60, help="How often to check for mentions in seconds (default: 60)")
@click.option("--once", is_flag=True, help="Process mentions once and exit (don't poll)")
@click.option("--console/--no-console", "use_console", default=True, help="Use rich console formatting (default: true)")
@click.option("--timeout", type=int, default=300, help="Timeout for agent response generation in seconds (default: 300 = 5 min)")
def process_agent_mentions(project_name: str, agents_project: str, poll_interval: int, once: bool, use_console: bool, timeout: int) -> None:
    """Monitor a project for @-mentions of agents and respond.

    This command:
    1. Loads agent definitions from the Agents project
    2. Monitors tasks and comments in the specified project
    3. When an agent is @-mentioned, generates a response using that agent's prompt
    4. Posts the response as a comment and reacts to the original mention
    """
    # Override console setting if specified at command level
    console.set_enabled(use_console)

    async def _process_mentions() -> None:
        import os
        import subprocess

        from aegis.asana.client import AsanaClient

        try:
            settings = get_settings()
            asana_client = AsanaClient(settings.asana_access_token)

            # Get the target project
            import asana
            configuration = asana.Configuration()
            configuration.access_token = settings.asana_access_token
            api_client = asana.ApiClient(configuration)
            portfolios_api = asana.PortfoliosApi(api_client)

            projects_generator = await asyncio.to_thread(
                portfolios_api.get_items_for_portfolio,
                settings.asana_portfolio_gid,
                {"opt_fields": "name,gid,notes"}
            )
            projects_list = list(projects_generator)

            # Find the target project
            target_project = None
            agents_project_obj = None
            for proj in projects_list:
                if proj["name"].lower() == project_name.lower():
                    target_project = proj
                if proj["name"].lower() == agents_project.lower():
                    agents_project_obj = proj

            if not target_project:
                console.print(f"[red]Error: Project '{project_name}' not found[/red]")
                sys.exit(1)

            if not agents_project_obj:
                console.print(f"[red]Error: Agents project '{agents_project}' not found[/red]")
                console.print("Run 'aegis create-agents-project' first to create it")
                sys.exit(1)

            console.print(f"[bold]Monitoring project: {target_project['name']}[/bold]")
            console.print(f"Agent definitions from: {agents_project_obj['name']}\n")

            # Track processed comments to avoid duplicates
            processed_comments = set()

            while True:
                try:
                    # Load agent definitions
                    agents = await asana_client.get_teammates_from_project(agents_project_obj["gid"])

                    if not agents:
                        console.print(f"[yellow]Warning: No agents found in '{agents_project}' project[/yellow]")
                        if once:
                            break
                        await asyncio.sleep(poll_interval)
                        continue

                    console.print(f"[dim]Loaded {len(agents)} agents: {', '.join(agents.keys())}[/dim]")

                    # Get all tasks from the target project
                    tasks = await asana_client.get_tasks_from_project(target_project["gid"], assigned_only=False)

                    # Process each task
                    for task in tasks:
                        if task.completed:
                            continue

                        # Check task name and notes for mentions
                        text_to_check = f"{task.name} {task.notes or ''}"
                        asana_client.extract_mentions_from_text(text_to_check)

                        # Get comments on the task
                        comments = await asana_client.get_comments(task.gid)

                        # Process each comment for mentions
                        for comment in comments:
                            # Skip if already processed
                            if comment.gid in processed_comments:
                                continue

                            # Extract mentions from comment
                            comment_mentions = asana_client.extract_mentions_from_text(comment.text)

                            # Check if any mentioned names match our agents
                            for mentioned_name in comment_mentions:
                                if mentioned_name in agents:
                                    console.print(f"\n[bold cyan]Found mention of '{mentioned_name}' in task: {task.name}[/bold cyan]")
                                    console.print(f"Comment by {comment.created_by.name}: {comment.text[:100]}...")

                                    # Get the agent's prompt
                                    agent_task = agents[mentioned_name]
                                    agent_prompt = agent_task.notes or "You are a helpful assistant."

                                    # Build context for the agent
                                    context = f"""Task: {task.name}
Task Description: {task.notes or '(none)'}
Task URL: {task.permalink_url}

Comment by {comment.created_by.name}:
{comment.text}

Your role/prompt:
{agent_prompt}

Please respond to the comment based on your role and the task context.
Keep your response concise and helpful."""

                                    # Extract code path from project notes
                                    code_path = None
                                    if target_project.get("notes"):
                                        for line in target_project["notes"].split("\n"):
                                            if line.startswith("Code Location:"):
                                                code_path = line.split(":", 1)[1].strip()
                                                code_path = os.path.expanduser(code_path)
                                                break

                                    working_dir = code_path if code_path and os.path.isdir(code_path) else None

                                    # Call Claude to generate response
                                    console.print(f"[dim]Generating response as '{mentioned_name}' (timeout: {timeout}s)...[/dim]")

                                    try:
                                        result = subprocess.run(
                                            ["claude", "--dangerously-skip-permissions", context],
                                            capture_output=True,
                                            text=True,
                                            timeout=timeout,
                                            cwd=working_dir
                                        )

                                        response = result.stdout.strip()

                                        if result.returncode == 0 and response:
                                            # Post the response as a comment
                                            response_text = f"[@{mentioned_name} responding]\n\n{response}"
                                            await asana_client.add_comment(task.gid, response_text)
                                            console.print("[green]✓ Posted response[/green]")

                                            # Try to add a thumbs-up reaction to the original comment
                                            try:
                                                await asana_client.add_reaction_to_story(comment.gid)
                                                console.print("[green]✓ Added reaction to comment[/green]")
                                            except Exception as e:
                                                console.print(f"[yellow]Warning: Could not add reaction: {e}[/yellow]")
                                        else:
                                            console.print(f"[yellow]Warning: Agent '{mentioned_name}' failed to generate response (exit code: {result.returncode})[/yellow]")
                                            if result.stderr:
                                                console.print(f"[dim]STDERR: {result.stderr[:200]}[/dim]")

                                    except subprocess.TimeoutExpired:
                                        console.print(f"[red]✗ Agent '{mentioned_name}' timed out after {timeout} seconds[/red]")
                                        console.print("[yellow]Suggestions:[/yellow]")
                                        console.print(f"  • Increase timeout: --timeout {timeout * 2}")
                                        console.print("  • Simplify the agent's prompt")

                                        # Post timeout notification to Asana
                                        timeout_message = f"[@{mentioned_name} timeout]\n\nAgent response generation timed out after {timeout} seconds. Try increasing timeout with `--timeout {timeout * 2}`"
                                        try:
                                            await asana_client.add_comment(task.gid, timeout_message)
                                        except Exception as e:
                                            console.print(f"[yellow]Warning: Failed to post timeout comment: {e}[/yellow]")

                                    # Mark comment as processed
                                    processed_comments.add(comment.gid)

                    if once:
                        console.print("\n[dim]Single pass complete (--once flag set)[/dim]")
                        break

                    # Wait before next poll
                    console.print(f"[dim]Sleeping {poll_interval}s until next check...[/dim]\n")
                    await asyncio.sleep(poll_interval)

                except KeyboardInterrupt:
                    console.print("\n[yellow]Interrupted by user[/yellow]")
                    break
                except Exception as e:
                    console.print(f"[red]Error processing mentions: {e}[/red]")
                    if once:
                        raise
                    # Continue polling on error
                    await asyncio.sleep(poll_interval)

        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    asyncio.run(_process_mentions())


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--port", default=0, type=int, help="Port to bind to (0 = dynamic)")
def agent_service(host: str, port: int) -> None:
    """Run an agent web service for task execution.

    This starts a standalone agent process that exposes an HTTP API for:
    - POST /execute - Execute a task
    - GET /status/{task_id} - Get task status
    - POST /cancel/{task_id} - Cancel a task
    - GET /health - Health check

    The agent will print its assigned port to stdout in the format:
    AGENT_PORT=<port>

    This command is typically used by the orchestrator to spawn agent processes,
    but can also be run manually for testing.

    Examples:
        # Run with dynamic port (OS assigns)
        aegis agent-service

        # Run on specific port
        aegis agent-service --port 9000

        # Bind to all interfaces
        aegis agent-service --host 0.0.0.0
    """
    from aegis.agents.agent_service import run_agent_service

    try:
        console.print(f"[cyan]Starting agent service on {host}:{port if port else 'dynamic'}...[/cyan]")
        run_agent_service(host=host, port=port)
    except KeyboardInterrupt:
        console.print("\n[yellow]Agent service stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
