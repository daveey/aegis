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
        console.print(f"Monitored Projects: {len(settings.asana_project_gids)}")
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
@click.option("--project-gid", help="Asana project GID to test (uses config if not provided)")
def test_asana(project_gid: str | None) -> None:
    """Test Asana API connection."""

    async def _test() -> None:
        from aegis.asana import AsanaClient

        try:
            settings = get_settings()
            test_project_gid = project_gid or (
                settings.asana_project_gids[0] if settings.asana_project_gids else None
            )

            if not test_project_gid:
                console.print("[red]No project GID provided or found in config[/red]")
                sys.exit(1)

            console.print(f"[bold]Testing Asana connection to project: {test_project_gid}[/bold]")

            client = AsanaClient(settings.asana_access_token)

            # Test fetching project
            console.print("Fetching project details...")
            project = await client.get_project(test_project_gid)
            console.print(f"[green]✓[/green] Project: {project.name}")

            # Test fetching tasks
            console.print("Fetching tasks...")
            tasks = await client.get_tasks_from_project(test_project_gid)
            console.print(f"[green]✓[/green] Found {len(tasks)} tasks")

            if tasks:
                console.print(f"\nFirst task: {tasks[0].name}")
                console.print(f"  Status: {'Complete' if tasks[0].completed else 'Incomplete'}")
                console.print(
                    f"  Assignee: {tasks[0].assignee.name if tasks[0].assignee else 'Unassigned'}"
                )

            console.print("\n[bold green]Asana API connection successful![/bold green]")

        except Exception as e:
            console.print(f"[red]Error testing Asana connection: {e}[/red]")
            sys.exit(1)

    asyncio.run(_test())


@main.command()
def test_claude() -> None:
    """Test Claude API connection."""
    console.print("[bold]Testing Claude API connection...[/bold]")
    console.print("[yellow]Note: Claude client not yet implemented[/yellow]")
    # TODO: Implement Claude client test


if __name__ == "__main__":
    main()
