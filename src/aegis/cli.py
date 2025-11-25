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


if __name__ == "__main__":
    main()
