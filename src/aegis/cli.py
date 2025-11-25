"""Command-line interface for Aegis."""

import asyncio
import sys

import click
import structlog
from rich.console import Console

from aegis.config import get_settings

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

    async def _do() -> None:
        import asana
        import subprocess
        import os
        from datetime import datetime
        from pathlib import Path

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
            projects_generator = await asyncio.to_thread(
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
            project_details = await asyncio.to_thread(
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
            tasks_generator = await asyncio.to_thread(
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

            # Set up logging
            logs_dir = Path.cwd() / "logs"
            logs_dir.mkdir(exist_ok=True)
            log_file = logs_dir / f"{project_name.lower()}.log"

            timestamp = datetime.now().isoformat()
            log_header = f"\n{'='*80}\n[{timestamp}] Task: {first_task['name']}\n{'='*80}\n\n"

            console.print("[bold]Executing task with Claude CLI...[/bold]\n")
            console.print("[dim]" + "=" * 60 + "[/dim]")
            console.print(f"[dim]Logging to: {log_file}[/dim]\n")

            # Execute Claude CLI and capture output
            # Change to code directory if available
            working_dir = code_path if code_path and os.path.isdir(code_path) else None

            try:
                result = subprocess.run(
                    [
                        "claude",
                        "--dangerously-skip-permissions",
                        "--output-format",
                        "stream-json",
                        task_context,
                    ],
                    cwd=working_dir,
                    check=False,
                    text=True,
                    capture_output=True,
                )

                # Combine stdout and stderr
                output = result.stdout
                if result.stderr:
                    output += f"\n\nSTDERR:\n{result.stderr}"

                # Write to log file
                with open(log_file, "a") as f:
                    f.write(log_header)
                    f.write(output)
                    f.write(f"\n\nExit code: {result.returncode}\n")

                console.print("[dim]" + "=" * 60 + "[/dim]\n")

                if result.returncode == 0:
                    console.print("[bold green]✓ Task execution completed[/bold green]")

                    # Post comment to Asana task
                    console.print("Posting results to Asana...")

                    # Create a summary comment
                    comment_text = f"""✓ Task completed via Aegis

**Timestamp**: {timestamp}

**Output**:
```
{output[:60000] if output else '(No output captured)'}
```

**Log file**: `{log_file}`
"""

                    comment_data = {
                        "data": {
                            "text": comment_text,
                        }
                    }

                    await asyncio.to_thread(
                        stories_api.create_story_for_task,
                        first_task["gid"],
                        comment_data,
                        {},
                    )

                    console.print("[green]✓[/green] Comment posted to Asana task\n")

                else:
                    console.print(
                        f"[yellow]Claude CLI exited with code {result.returncode}[/yellow]"
                    )

                    # Still post a comment about the failure
                    comment_text = f"""⚠️ Task execution completed with errors (exit code {result.returncode})

**Timestamp**: {timestamp}

**Output**:
```
{output[:60000] if output else '(No output captured)'}
```

**Log file**: `{log_file}`
"""

                    comment_data = {
                        "data": {
                            "text": comment_text,
                        }
                    }

                    await asyncio.to_thread(
                        stories_api.create_story_for_task,
                        first_task["gid"],
                        comment_data,
                        {},
                    )

                    console.print("[yellow]⚠[/yellow] Comment posted to Asana task\n")

            except FileNotFoundError:
                console.print(
                    "[red]Error: 'claude' CLI not found. Please install it first.[/red]"
                )
                console.print("Install with: npm install -g @anthropic-ai/claude-cli")
                sys.exit(1)

        except Exception as e:
            console.print(f"[red]Error executing task: {e}[/red]")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    asyncio.run(_do())


if __name__ == "__main__":
    main()
