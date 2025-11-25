"""Command-line interface for Aegis."""

import asyncio
import sys

import click
import structlog
from rich.console import Console
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import asana.rest

from aegis.config import get_settings
from aegis.utils.shutdown import get_shutdown_handler
from aegis.database.session import cleanup_db_connections
from aegis.database.state import (
    mark_orchestrator_stopped_async,
    mark_orchestrator_running,
)

console = Console()
logger = structlog.get_logger()


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """Aegis - Intelligent assistant orchestration system."""
    pass


@main.command()
def config() -> None:
    """Display current configuration."""
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
def start() -> None:
    """Start the Aegis orchestrator."""
    console.print("[bold green]Starting Aegis...[/bold green]")
    console.print("[yellow]Note: Main orchestration loop not yet implemented[/yellow]")
    # TODO: Implement main orchestration loop
    # asyncio.run(orchestrator.run())


@main.command()
def test_asana() -> None:
    """Test Asana API connection and list portfolio projects."""

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
@click.argument("project_name")
def do(project_name: str) -> None:
    """Pick the first task from a project and execute it using Claude CLI."""

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
        import asana
        import subprocess
        import os

        # Initialize shutdown handler
        shutdown_handler = get_shutdown_handler(shutdown_timeout=300)
        shutdown_handler.install_signal_handlers()

        # Register cleanup callbacks
        shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
        shutdown_handler.register_cleanup_callback(cleanup_db_connections)

        try:
            settings = get_settings()
            portfolio_gid = settings.asana_portfolio_gid

            console.print(f"[bold]Finding project '{project_name}'...[/bold]")

            # Configure API client
            configuration = asana.Configuration()
            configuration.access_token = settings.asana_access_token
            api_client = asana.ApiClient(configuration)
            portfolios_api = asana.PortfoliosApi(api_client)
            projects_api = asana.ProjectsApi(api_client)
            tasks_api = asana.TasksApi(api_client)
            stories_api = asana.StoriesApi(api_client)

            # Get projects from portfolio
            projects_generator = await fetch_with_retry(
                portfolios_api.get_items_for_portfolio, portfolio_gid, {"opt_fields": "name,gid"}
            )
            projects_list = list(projects_generator)

            # Find matching project (case-insensitive)
            project = None
            for proj in projects_list:
                if proj["name"].lower() == project_name.lower():
                    project = proj
                    break

            if not project:
                console.print(f"[red]Error: Project '{project_name}' not found in portfolio[/red]")
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

            # Format task context for Claude CLI
            task_context = f"""Task: {first_task['name']}

Project: {project['name']}"""

            if code_path:
                task_context += f"\nCode Location: {code_path}"

            if first_task.get("notes"):
                task_context += f"\n\nTask Description:\n{first_task['notes']}"

            # Determine working directory
            working_dir = code_path if code_path and os.path.isdir(code_path) else None

            # Set up logging
            from datetime import datetime
            from pathlib import Path

            logs_dir = Path.cwd() / "logs"
            logs_dir.mkdir(exist_ok=True)
            log_file = logs_dir / f"{project_name.lower()}.log"
            timestamp = datetime.now().isoformat()

            console.print("[bold]Executing task with Claude CLI...[/bold]\n")
            console.print(f"[dim]Task: {first_task['name']}[/dim]")
            console.print(f"[dim]Working directory: {working_dir or 'current directory'}[/dim]")
            console.print(f"[dim]Logging to: {log_file}[/dim]\n")
            console.print("[dim]" + "=" * 60 + "[/dim]\n")

            try:
                # Run claude with output capture (non-interactive)
                result = subprocess.run(
                    ["claude", "--dangerously-skip-permissions", task_context],
                    cwd=working_dir,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                # Combine output
                output = result.stdout
                if result.stderr:
                    output += f"\n\nSTDERR:\n{result.stderr}"

                # Write to log file
                log_header = f"\n{'='*80}\n[{timestamp}] Task: {first_task['name']}\n{'='*80}\n\n"
                try:
                    with open(log_file, "a") as f:
                        f.write(log_header)
                        f.write(output)
                        f.write(f"\n\nExit code: {result.returncode}\n")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Failed to write to log: {e}")

                console.print("\n" + "[dim]" + "=" * 60 + "[/dim]\n")

                # Post comment to Asana
                console.print("Posting results to Asana...")

                status_emoji = "✓" if result.returncode == 0 else "⚠️"
                status_text = "completed" if result.returncode == 0 else f"completed with errors (exit code {result.returncode})"

                comment_text = f"""{status_emoji} Task {status_text} via Aegis

**Timestamp**: {timestamp}

**Output**:
```
{output[:60000] if output else '(No output captured)'}
```

**Log file**: `{log_file}`
"""

                comment_data = {"data": {"text": comment_text}}

                try:
                    await post_asana_comment(stories_api, comment_data, first_task["gid"])
                    console.print("[green]✓[/green] Comment posted to Asana\n")
                except Exception as e:
                    console.print(f"[yellow]⚠[/yellow] Failed to post comment: {e}\n")

                if result.returncode == 0:
                    console.print("[bold green]✓ Task execution completed[/bold green]\n")
                else:
                    console.print(
                        f"[yellow]Claude CLI exited with code {result.returncode}[/yellow]\n"
                    )

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

    asyncio.run(_do())


@main.command()
@click.argument("project_name")
@click.option("--max-tasks", default=5, help="Maximum tasks to execute in one session")
@click.option("--dry-run", is_flag=True, help="Show what would be done without executing")
def work_on(project_name: str, max_tasks: int, dry_run: bool) -> None:
    """Autonomous work on a project - assess state, ask questions, do ready tasks."""

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
        import asana
        import subprocess
        import os
        from datetime import datetime
        from pathlib import Path

        # Initialize shutdown handler
        shutdown_handler = get_shutdown_handler(shutdown_timeout=300)
        shutdown_handler.install_signal_handlers()

        # Register cleanup callbacks
        shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
        shutdown_handler.register_cleanup_callback(cleanup_db_connections)

        try:
            settings = get_settings()
            portfolio_gid = settings.asana_portfolio_gid

            # Mark as running (optional, for when full orchestrator is implemented)
            try:
                mark_orchestrator_running()
            except Exception as e:
                logger.warning("failed_to_mark_running", error=str(e))

            console.print(f"[bold]Analyzing {project_name} project...[/bold]")

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
                if proj["name"].lower() == project_name.lower():
                    project = proj
                    break

            if not project:
                console.print(f"[red]Error: Project '{project_name}' not found in portfolio[/red]")
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

            # Categorize tasks
            incomplete_unassigned = []
            for task in tasks_list:
                if not task.get("completed") and not task.get("assignee"):
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

            # Create question tasks if needed
            if questions_needed:
                console.print(f"\n[bold]Creating question tasks...[/bold]")
                me = await asyncio.to_thread(users_api.get_user, "me", {})
                me_gid = me["gid"]

                for q_type, q_details in questions_needed.items():
                    question_text = f"""**From**: Claude (Aegis Autonomous Agent)
**Context**: Working on project assessment
**Blocker**: {q_details['reason']}

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
                            "name": f"Question: {q_details['question']}",
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

                # Now create dependencies for all blocked tasks
                console.print(f"\n[bold]Creating Asana dependencies...[/bold]")
                for q_type, q_details in questions_needed.items():
                    if "task_gid" in q_details and "blocked_task_gids" in q_details:
                        question_gid = q_details["task_gid"]
                        for blocked_task_gid in q_details["blocked_task_gids"]:
                            try:
                                # Add dependency: blocked_task depends on question_task
                                await asyncio.to_thread(
                                    tasks_api.add_dependencies_for_task,
                                    {"data": {"dependencies": [question_gid]}},
                                    blocked_task_gid,
                                    {}
                                )
                                console.print(f"  ✓ Made task {blocked_task_gid[:8]}... depend on question")
                            except Exception as e:
                                logger.warning("failed_to_create_dependency",
                                             task_gid=blocked_task_gid,
                                             question_gid=question_gid,
                                             error=str(e))

            # Execute ready tasks (up to max_tasks)
            if ready_tasks:
                tasks_to_execute = ready_tasks[:max_tasks]
                console.print(f"\n[bold]Executing {len(tasks_to_execute)} ready task(s)...[/bold]\n")

                working_dir = code_path if code_path and os.path.isdir(code_path) else None

                logs_dir = Path.cwd() / "logs"
                logs_dir.mkdir(exist_ok=True)
                log_file = logs_dir / f"{project_name.lower()}.log"

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

Project: {project['name']}"""

                    if code_path:
                        task_context += f"\nCode Location: {code_path}"

                    if task.get("notes"):
                        task_context += f"\n\nTask Description:\n{task['notes']}"

                    timestamp = datetime.now().isoformat()

                    try:
                        # Run claude with output capture
                        result = subprocess.run(
                            ["claude", "--dangerously-skip-permissions", task_context],
                            cwd=working_dir,
                            check=False,
                            capture_output=True,
                            text=True,
                            timeout=300,  # 5 minute timeout per task
                        )

                        output = result.stdout
                        if result.stderr:
                            output += f"\n\nSTDERR:\n{result.stderr}"

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
                            console.print(f"  [green]✓ Completed[/green]\n")
                            completed_count += 1
                        else:
                            console.print(f"  [yellow]⚠ Completed with warnings[/yellow]\n")
                            failed_count += 1

                    except subprocess.TimeoutExpired:
                        console.print(f"  [red]✗ Timeout (5 minutes)[/red]\n")
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


if __name__ == "__main__":
    main()
