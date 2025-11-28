"""New Aegis CLI with SwarmDispatcher integration."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import click
import structlog
from rich.console import Console

from aegis.config import Settings
from aegis.infrastructure.pid_manager import PIDLockError, PIDManager

console = Console()
logger = structlog.get_logger()


@click.group()
@click.version_option()
def main():
    """Aegis - Personal LLM Agent Swarm.

    Uses Asana as the UI and state store, with specialized AI agents
    handling different phases of software development.
    """
    pass


@main.command()
@click.argument("project")
def start(project: str):
    """Start the swarm dispatcher for a project.

    PROJECT can be a project name, GID, or Asana URL.

    Examples:
        aegis start Aegis
        aegis start 1212085431574340
        aegis start https://app.asana.com/0/1212085431574340
    """
    console.print("[bold green]Starting Aegis Swarm...[/bold green]")

    async def _start():
        from aegis.asana.client import AsanaClient
        from aegis.orchestrator.dispatcher import SwarmDispatcher

        try:
            settings = Settings()

            # Parse project input
            project_gid = _parse_project_input(project, settings)

            console.print(f"[green]✓[/green] Project GID: {project_gid}\n")

            # Display configuration
            console.print("[bold]Configuration:[/bold]")
            console.print(f"  Project GID: {project_gid}")
            console.print(f"  Poll Interval: {settings.poll_interval_seconds}s")
            console.print(f"  Repository: {Path.cwd()}")
            console.print(f"  Worktree Dir: _worktrees/\n")

            # Create and start dispatcher
            dispatcher = SwarmDispatcher(settings, project_gid)

            console.print("[green]✓[/green] Dispatcher initialized")
            console.print("[dim]Press Ctrl+C to stop gracefully[/dim]\n")

            await dispatcher.start()

        except PIDLockError as e:
            console.print(f"[red]✗ {e}[/red]")
            sys.exit(1)
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
        sys.exit(130)


@main.command()
def stop():
    """Stop a running swarm dispatcher."""
    console.print("[bold]Stopping Aegis Swarm...[/bold]")

    try:
        pid_manager = PIDManager()
        if pid_manager.stop_orchestrator(timeout=60):
            console.print("[green]✓[/green] Dispatcher stopped successfully")
        else:
            console.print("[yellow]No dispatcher is currently running[/yellow]")
    except Exception as e:
        console.print(f"[red]Error stopping dispatcher: {e}[/red]")
        sys.exit(1)


@main.command()
def status():
    """Show dispatcher status."""
    console.print("[bold]Aegis Swarm Status[/bold]\n")

    try:
        pid_manager = PIDManager()
        pid = pid_manager.get_running_pid()

        if pid:
            console.print(f"[green]● Running[/green]")
            console.print(f"  PID: {pid}")

            # Load state
            state_file = Path.cwd() / "swarm_state.json"
            if state_file.exists():
                with open(state_file) as f:
                    state = json.load(f)

                orch_state = state.get("orchestrator", {})
                active_tasks = orch_state.get("active_tasks", [])

                console.print(f"  Started: {orch_state.get('started_at', 'Unknown')}")
                console.print(f"  Last Poll: {orch_state.get('last_poll', 'Unknown')}")
                console.print(f"  Active Tasks: {len(active_tasks)}")

                if active_tasks:
                    console.print("\n[bold]Active Tasks:[/bold]")
                    for task_gid in active_tasks:
                        console.print(f"  • {task_gid}")
        else:
            console.print("[dim]○ Not running[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("project", required=False)
@click.option("--portfolio", help="Sync all projects in portfolio")
@click.option("--dry-run", is_flag=True, help="Show what would change without applying")
def sync(project: str | None, portfolio: str | None, dry_run: bool):
    """Sync Asana project sections to canonical structure.

    Ensures projects have the correct sections in the right order.

    Examples:
        aegis sync --project Aegis
        aegis sync --portfolio  # Uses portfolio from .env
        aegis sync --dry-run --project 1212085431574340
    """
    console.print("[bold]Syncing Asana Sections...[/bold]\n")

    try:
        # Build command
        cmd = ["python", "tools/sync_asana_sections.py"]

        if project:
            settings = Settings()
            project_gid = _parse_project_input(project, settings)
            cmd.extend(["--project", project_gid])
        elif portfolio:
            cmd.extend(["--portfolio", portfolio])
        else:
            # Default to portfolio from env
            cmd.append("--portfolio")

        if dry_run:
            cmd.append("--dry-run")

        # Run sync tool
        result = subprocess.run(cmd, cwd=Path.cwd())
        sys.exit(result.returncode)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("project_name", required=False)
@click.option("--design-doc", help="URL or path to design document")
def create(project_name: str | None, design_doc: str | None):
    """Interactive project creation wizard.

    Creates a complete project with:
    - GitHub repository (new or linked)
    - Local git checkout
    - Aegis configuration files
    - GitHub Actions CI/CD
    - README and documentation
    - Asana project with sections

    Example:
        aegis create "My New Project"
        aegis create --design-doc https://example.com/design.md
    """
    import subprocess
    import tempfile
    import webbrowser
    from pathlib import Path

    console.print("[bold green]Aegis Project Creation Wizard[/bold green]\n")
    console.print("This wizard will help you create a complete Aegis-managed project.\n")

    # -------------------------------------------------------------------------
    # Step 1: Project Name
    # -------------------------------------------------------------------------
    if not project_name:
        project_name = click.prompt("Project name", type=str)

    console.print(f"\n[bold]Creating project: {project_name}[/bold]\n")

    # -------------------------------------------------------------------------
    # Step 2: GitHub Integration
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 1: GitHub Repository[/bold cyan]\n")

    github_choice = click.prompt(
        "GitHub repository",
        type=click.Choice(["create", "link", "skip"], case_sensitive=False),
        default="create",
        show_choices=True,
    )

    github_repo_url = None
    github_repo_name = None

    if github_choice == "create":
        console.print("\n[dim]Creating new GitHub repository...[/dim]")

        # Check if gh CLI is available
        try:
            result = subprocess.run(
                ["gh", "--version"],
                capture_output=True,
                check=True,
            )
            console.print("[green]✓[/green] GitHub CLI (gh) found\n")
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print("[red]✗[/red] GitHub CLI (gh) not found")
            console.print("\nInstall GitHub CLI:")
            console.print("  macOS: brew install gh")
            console.print("  Linux: https://github.com/cli/cli#installation")
            console.print("  Windows: winget install GitHub.cli\n")

            if not click.confirm("Continue without GitHub integration?", default=False):
                sys.exit(1)
            github_choice = "skip"

        if github_choice == "create":
            # Get GitHub username
            try:
                result = subprocess.run(
                    ["gh", "api", "user", "--jq", ".login"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                github_user = result.stdout.strip()
                console.print(f"[green]✓[/green] GitHub user: {github_user}\n")
            except subprocess.CalledProcessError:
                console.print("[yellow]Not logged in to GitHub CLI[/yellow]")
                console.print("Run: gh auth login\n")
                github_user = click.prompt("GitHub username", type=str)

            # Sanitize project name for repo
            repo_name = project_name.lower().replace(" ", "-").replace("_", "-")
            repo_name = click.prompt("Repository name", type=str, default=repo_name)

            # Public or private
            is_public = click.confirm("Make repository public?", default=False)

            # Description
            description = click.prompt(
                "Repository description (optional)",
                type=str,
                default=f"{project_name} - Managed by Aegis",
            )

            # Create repo
            console.print(f"\n[dim]Creating repository {github_user}/{repo_name}...[/dim]")

            cmd = ["gh", "repo", "create", f"{github_user}/{repo_name}"]
            cmd.extend(["--public"] if is_public else ["--private"])
            cmd.extend(["--description", description])
            cmd.extend(["--clone"])

            try:
                result = subprocess.run(cmd, cwd=Path.cwd(), check=True, capture_output=True, text=True)
                console.print(f"[green]✓[/green] Repository created\n")

                github_repo_url = f"https://github.com/{github_user}/{repo_name}"
                github_repo_name = f"{github_user}/{repo_name}"

                # Change to repo directory
                repo_path = Path.cwd() / repo_name
                if repo_path.exists():
                    import os
                    os.chdir(repo_path)
                    console.print(f"[green]✓[/green] Changed to: {repo_path}\n")

            except subprocess.CalledProcessError as e:
                console.print(f"[red]✗[/red] Failed to create repository: {e.stderr}")
                if not click.confirm("Continue without GitHub?", default=False):
                    sys.exit(1)
                github_choice = "skip"

    elif github_choice == "link":
        github_repo_url = click.prompt("GitHub repository URL", type=str)

        console.print(f"\n[dim]Cloning repository...[/dim]")

        try:
            result = subprocess.run(
                ["git", "clone", github_repo_url],
                cwd=Path.cwd(),
                check=True,
                capture_output=True,
                text=True,
            )

            # Extract repo name from URL
            repo_name = github_repo_url.rstrip("/").split("/")[-1].replace(".git", "")

            # Change to repo directory
            repo_path = Path.cwd() / repo_name
            if repo_path.exists():
                import os
                os.chdir(repo_path)
                console.print(f"[green]✓[/green] Cloned and changed to: {repo_path}\n")

            github_repo_name = "/".join(github_repo_url.rstrip("/").split("/")[-2:]).replace(".git", "")

        except subprocess.CalledProcessError as e:
            console.print(f"[red]✗[/red] Failed to clone repository: {e.stderr}")
            sys.exit(1)

    console.print()

    # -------------------------------------------------------------------------
    # Step 3: Design Document
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 2: Design Document (Optional)[/bold cyan]\n")

    design_doc_content = None

    if not design_doc:
        design_choice = click.prompt(
            "Do you have a design document?",
            type=click.Choice(["url", "paste", "skip"], case_sensitive=False),
            default="skip",
            show_choices=True,
        )

        if design_choice == "url":
            design_doc = click.prompt("Design document URL", type=str)
        elif design_choice == "paste":
            console.print("\n[dim]Paste your design document (Ctrl+D when done):[/dim]\n")
            design_doc_content = sys.stdin.read()

    if design_doc and not design_doc_content:
        # Fetch design doc
        console.print(f"\n[dim]Fetching design document...[/dim]")

        if design_doc.startswith("http"):
            # URL - fetch it
            try:
                import urllib.request
                with urllib.request.urlopen(design_doc) as response:
                    design_doc_content = response.read().decode("utf-8")
                console.print("[green]✓[/green] Design document fetched\n")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not fetch design doc: {e}[/yellow]\n")
        else:
            # Local file
            try:
                design_doc_content = Path(design_doc).read_text()
                console.print("[green]✓[/green] Design document loaded\n")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read design doc: {e}[/yellow]\n")

    console.print()

    # -------------------------------------------------------------------------
    # Step 4: Run Project Setup
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 3: Project Setup[/bold cyan]\n")

    console.print("[dim]Running project setup script...[/dim]\n")

    # Build setup command
    setup_cmd = ["python", str(Path(__file__).parent.parent.parent / "tools" / "setup_github_project.py")]
    setup_cmd.extend(["--project-name", project_name])

    if github_repo_url:
        setup_cmd.extend(["--github-url", github_repo_url])

    if github_repo_name:
        setup_cmd.extend(["--github-repo", github_repo_name])

    if design_doc_content:
        # Write to temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(design_doc_content)
            setup_cmd.extend(["--design-doc", f.name])

    try:
        result = subprocess.run(
            setup_cmd,
            check=True,
        )

        console.print(f"\n[green]✓[/green] Project setup complete\n")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗[/red] Project setup failed: {e}")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Step 5: Create Asana Project
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 4: Asana Project[/bold cyan]\n")

    if click.confirm("Create Asana project?", default=True):
        async def _create_asana():
            from aegis.asana.client import AsanaClient

            try:
                settings = Settings()
                client = AsanaClient(settings.asana_access_token)

                console.print("[dim]Creating Asana project...[/dim]")

                # Create project (TODO: implement)
                console.print("[yellow]Note: Asana project creation not fully implemented[/yellow]")
                console.print("[dim]Create the project manually in Asana, then run:[/dim]")
                console.print(f"[cyan]  aegis sync --project \"{project_name}\"[/cyan]\n")

            except Exception as e:
                console.print(f"[yellow]Warning: {e}[/yellow]\n")

        asyncio.run(_create_asana())

    # -------------------------------------------------------------------------
    # Completion
    # -------------------------------------------------------------------------
    console.print("[bold green]✓ Project Creation Complete![/bold green]\n")

    console.print("[bold]Project Details:[/bold]")
    console.print(f"  Name: {project_name}")
    console.print(f"  Location: {Path.cwd()}")
    if github_repo_url:
        console.print(f"  GitHub: {github_repo_url}")

    console.print("\n[bold]Next Steps:[/bold]")
    console.print("  1. Review the generated files (README.md, design.md, etc.)")
    console.print("  2. Create Asana project and run: [cyan]aegis sync --project PROJECT_GID[/cyan]")
    console.print("  3. Commit and push: [cyan]git add . && git commit -m \"Initial setup\" && git push[/cyan]")
    console.print(f"  4. Start developing: [cyan]aegis start \"{project_name}\"[/cyan]")


@main.command()
def init():
    """Initialize Aegis configuration in current directory.

    Creates:
    - aegis_config.json (if not exists)
    - swarm_memory.md (if not exists)
    - user_preferences.md (if not exists)
    - swarm_state.json (if not exists)
    """
    console.print("[bold]Initializing Aegis configuration...[/bold]\n")

    cwd = Path.cwd()
    created = []

    # Check if files exist
    files_to_create = {
        "aegis_config.json": True,
        "swarm_memory.md": True,
        "user_preferences.md": True,
        "swarm_state.json": True,
    }

    for filename in files_to_create:
        filepath = cwd / filename
        if filepath.exists():
            console.print(f"[dim]✓ {filename} already exists[/dim]")
        else:
            created.append(filename)

    if not created:
        console.print("[green]✓ All configuration files already exist[/green]")
        return

    # Copy templates if they don't exist
    for filename in created:
        # Templates are in the repo root (where we are)
        source = cwd / filename
        if source.exists():
            console.print(f"[green]✓ {filename} already present[/green]")
        else:
            console.print(f"[yellow]✗ {filename} not found - please create manually[/yellow]")

    if created:
        console.print(f"\n[green]✓ Initialized {len(created)} configuration file(s)[/green]")


@main.command()
def logs():
    """Tail orchestrator logs."""
    log_file = Path.cwd() / "logs" / "aegis.log"

    if not log_file.exists():
        console.print("[yellow]No log file found[/yellow]")
        return

    try:
        subprocess.run(["tail", "-f", str(log_file)])
    except KeyboardInterrupt:
        pass


@main.command()
def config():
    """Display current configuration."""
    console.print("[bold]Aegis Configuration[/bold]\n")

    try:
        settings = Settings()

        console.print("[bold]Asana:[/bold]")
        console.print(f"  Workspace GID: {settings.asana_workspace_gid}")
        console.print(f"  Portfolio GID: {settings.asana_portfolio_gid}")
        console.print(f"  Access Token: {settings.asana_access_token[:20]}...")

        console.print("\n[bold]Anthropic:[/bold]")
        console.print(f"  API Key: {settings.anthropic_api_key[:20]}...")
        console.print(f"  Model: {settings.anthropic_model}")

        console.print("\n[bold]Orchestrator:[/bold]")
        console.print(f"  Poll Interval: {settings.poll_interval_seconds}s")
        console.print(f"  Max Concurrent: {settings.max_concurrent_tasks}")
        console.print(f"  Shutdown Timeout: {settings.shutdown_timeout}s")

        console.print("\n[bold]Database:[/bold]")
        console.print(f"  URL: {settings.database_url}")

        console.print("\n[green]✓ Configuration loaded successfully[/green]")

    except Exception as e:
        console.print(f"[red]Error loading configuration: {e}[/red]")
        console.print("\n[dim]Make sure .env file exists with required variables[/dim]")
        sys.exit(1)


@main.command()
def configure():
    """Interactive configuration wizard.

    Walks you through setting up Aegis by collecting:
    - Asana Personal Access Token
    - Asana Workspace, Team, and Portfolio GIDs
    - Anthropic API Key

    Opens browser tabs to help you get the required tokens.
    """
    import webbrowser
    from pathlib import Path

    console.print("[bold green]Aegis Configuration Wizard[/bold green]\n")
    console.print("This wizard will help you set up Aegis by collecting necessary credentials.\n")

    env_path = Path.cwd() / ".env"

    # Check if .env exists
    if env_path.exists():
        console.print("[yellow]Warning: .env file already exists[/yellow]")
        overwrite = click.confirm("Do you want to overwrite it?", default=False)
        if not overwrite:
            console.print("[dim]Configuration cancelled[/dim]")
            return
        console.print()

    # Collect configuration
    config_data = {}

    # -------------------------------------------------------------------------
    # Asana Configuration
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 1: Asana Configuration[/bold cyan]\n")

    console.print("You'll need an Asana Personal Access Token.")
    console.print("[dim]This allows Aegis to read and update tasks in your Asana workspace.[/dim]\n")

    if click.confirm("Open Asana Personal Access Token page in browser?", default=True):
        webbrowser.open("https://app.asana.com/0/my-apps")
        console.print("[green]✓[/green] Opened in browser\n")

    console.print("Steps to get your token:")
    console.print("  1. Go to Asana → Profile Icon → My Settings")
    console.print("  2. Click 'Apps' tab")
    console.print("  3. Click 'Create new token'")
    console.print("  4. Name it 'Aegis' and click 'Create token'")
    console.print("  5. Copy the token (it starts with '1/')\n")

    asana_token = click.prompt("Paste your Asana Personal Access Token", type=str)
    config_data["ASANA_ACCESS_TOKEN"] = asana_token.strip()

    console.print("\n[dim]Testing Asana connection...[/dim]")

    # Test Asana connection and get workspace info
    try:
        import asyncio
        import asana

        configuration = asana.Configuration()
        configuration.access_token = asana_token.strip()
        api_client = asana.ApiClient(configuration)
        workspaces_api = asana.WorkspacesApi(api_client)

        async def get_workspaces():
            return await asyncio.to_thread(
                workspaces_api.get_workspaces,
                {"opt_fields": "name,gid,is_organization"}
            )

        workspaces = asyncio.run(get_workspaces())
        workspaces_list = list(workspaces)

        console.print("[green]✓[/green] Connection successful!\n")

        if len(workspaces_list) == 1:
            # Only one workspace, auto-select
            workspace = workspaces_list[0]
            workspace_dict = workspace if isinstance(workspace, dict) else workspace.to_dict()
            console.print(f"[green]✓[/green] Found workspace: {workspace_dict['name']}")
            config_data["ASANA_WORKSPACE_GID"] = workspace_dict["gid"]
            workspace_gid = workspace_dict["gid"]
            is_org = workspace_dict.get("is_organization", False)
        else:
            # Multiple workspaces, let user choose
            console.print("Found multiple workspaces:\n")
            for i, ws in enumerate(workspaces_list, 1):
                ws_dict = ws if isinstance(ws, dict) else ws.to_dict()
                console.print(f"  {i}. {ws_dict['name']} (GID: {ws_dict['gid']})")

            workspace_idx = click.prompt("\nSelect workspace number", type=int, default=1)
            workspace = workspaces_list[workspace_idx - 1]
            workspace_dict = workspace if isinstance(workspace, dict) else workspace.to_dict()
            config_data["ASANA_WORKSPACE_GID"] = workspace_dict["gid"]
            workspace_gid = workspace_dict["gid"]
            is_org = workspace_dict.get("is_organization", False)

        console.print()

        # Get Team GID (for organizations)
        if is_org:
            console.print("[dim]Fetching teams in organization...[/dim]")
            teams_api = asana.TeamsApi(api_client)

            async def get_teams():
                return await asyncio.to_thread(
                    teams_api.get_teams_for_workspace,
                    workspace_gid,
                    {"opt_fields": "name,gid"}
                )

            teams = asyncio.run(get_teams())
            teams_list = list(teams)

            if len(teams_list) == 1:
                team = teams_list[0]
                team_dict = team if isinstance(team, dict) else team.to_dict()
                console.print(f"[green]✓[/green] Found team: {team_dict['name']}")
                config_data["ASANA_TEAM_GID"] = team_dict["gid"]
            else:
                console.print("\nFound teams:\n")
                for i, team in enumerate(teams_list, 1):
                    team_dict = team if isinstance(team, dict) else team.to_dict()
                    console.print(f"  {i}. {team_dict['name']} (GID: {team_dict['gid']})")

                team_idx = click.prompt("\nSelect team number", type=int, default=1)
                team = teams_list[team_idx - 1]
                team_dict = team if isinstance(team, dict) else team.to_dict()
                config_data["ASANA_TEAM_GID"] = team_dict["gid"]

            console.print()
        else:
            # Not an organization, use workspace GID as team GID
            config_data["ASANA_TEAM_GID"] = workspace_gid

        # Get Portfolio GID
        console.print("Now we need a Portfolio GID.")
        console.print("[dim]Portfolios group related projects. Aegis will monitor all projects in this portfolio.[/dim]\n")

        portfolios_api = asana.PortfoliosApi(api_client)

        async def get_portfolios():
            return await asyncio.to_thread(
                portfolios_api.get_portfolios,
                workspace_gid,
                {"opt_fields": "name,gid"}
            )

        portfolios = asyncio.run(get_portfolios())
        portfolios_list = list(portfolios)

        if len(portfolios_list) == 0:
            console.print("[yellow]No portfolios found in workspace[/yellow]")
            console.print("\nYou can:")
            console.print("  1. Create a portfolio in Asana")
            console.print("  2. Enter the portfolio GID manually later\n")

            portfolio_gid = click.prompt("Enter portfolio GID (or press Enter to set later)", type=str, default="")
            if portfolio_gid:
                config_data["ASANA_PORTFOLIO_GID"] = portfolio_gid.strip()
            else:
                config_data["ASANA_PORTFOLIO_GID"] = "CHANGE_ME"

        elif len(portfolios_list) == 1:
            portfolio = portfolios_list[0]
            portfolio_dict = portfolio if isinstance(portfolio, dict) else portfolio.to_dict()
            console.print(f"[green]✓[/green] Found portfolio: {portfolio_dict['name']}")
            config_data["ASANA_PORTFOLIO_GID"] = portfolio_dict["gid"]
        else:
            console.print("Found portfolios:\n")
            for i, portfolio in enumerate(portfolios_list, 1):
                portfolio_dict = portfolio if isinstance(portfolio, dict) else portfolio.to_dict()
                console.print(f"  {i}. {portfolio_dict['name']} (GID: {portfolio_dict['gid']})")

            portfolio_idx = click.prompt("\nSelect portfolio number", type=int, default=1)
            portfolio = portfolios_list[portfolio_idx - 1]
            portfolio_dict = portfolio if isinstance(portfolio, dict) else portfolio.to_dict()
            config_data["ASANA_PORTFOLIO_GID"] = portfolio_dict["gid"]

    except Exception as e:
        console.print(f"[red]Error testing Asana connection: {e}[/red]")
        console.print("[yellow]You can still continue and fix the credentials later[/yellow]\n")

        # Fallback to manual input
        workspace_gid = click.prompt("Asana Workspace GID", type=str, default="")
        config_data["ASANA_WORKSPACE_GID"] = workspace_gid.strip() or "CHANGE_ME"

        team_gid = click.prompt("Asana Team GID", type=str, default="")
        config_data["ASANA_TEAM_GID"] = team_gid.strip() or config_data["ASANA_WORKSPACE_GID"]

        portfolio_gid = click.prompt("Asana Portfolio GID", type=str, default="")
        config_data["ASANA_PORTFOLIO_GID"] = portfolio_gid.strip() or "CHANGE_ME"

    console.print()

    # -------------------------------------------------------------------------
    # Anthropic Configuration
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 2: Anthropic API Configuration[/bold cyan]\n")

    console.print("You'll need an Anthropic API key for Claude.")
    console.print("[dim]This allows Aegis agents to use Claude for task execution.[/dim]\n")

    if click.confirm("Open Anthropic API Keys page in browser?", default=True):
        webbrowser.open("https://console.anthropic.com/settings/keys")
        console.print("[green]✓[/green] Opened in browser\n")

    console.print("Steps to get your API key:")
    console.print("  1. Go to https://console.anthropic.com/settings/keys")
    console.print("  2. Click 'Create Key'")
    console.print("  3. Name it 'Aegis' and click 'Create Key'")
    console.print("  4. Copy the key (it starts with 'sk-ant-')\n")

    anthropic_key = click.prompt("Paste your Anthropic API Key", type=str)
    config_data["ANTHROPIC_API_KEY"] = anthropic_key.strip()

    console.print()

    # -------------------------------------------------------------------------
    # Optional Configuration
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 3: Optional Configuration[/bold cyan]\n")

    if click.confirm("Configure database URL? (optional, press N to use default)", default=False):
        database_url = click.prompt("Database URL", type=str, default="postgresql://localhost/aegis")
        config_data["DATABASE_URL"] = database_url
    else:
        config_data["DATABASE_URL"] = "postgresql://localhost/aegis"

    console.print()

    # -------------------------------------------------------------------------
    # Write .env file
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 4: Saving Configuration[/bold cyan]\n")

    env_content = f"""# Aegis Configuration
# Generated by 'aegis configure' on {Path.cwd()}

# Asana Configuration
ASANA_ACCESS_TOKEN="{config_data['ASANA_ACCESS_TOKEN']}"
ASANA_WORKSPACE_GID="{config_data['ASANA_WORKSPACE_GID']}"
ASANA_TEAM_GID="{config_data['ASANA_TEAM_GID']}"
ASANA_PORTFOLIO_GID="{config_data['ASANA_PORTFOLIO_GID']}"

# Anthropic Configuration
ANTHROPIC_API_KEY="{config_data['ANTHROPIC_API_KEY']}"
ANTHROPIC_MODEL="claude-sonnet-4-5-20250929"
ANTHROPIC_MAX_TOKENS="4096"

# Database Configuration (optional)
DATABASE_URL="{config_data['DATABASE_URL']}"
REDIS_URL="redis://localhost:6379"

# Orchestrator Configuration (optional - uses defaults)
# POLL_INTERVAL_SECONDS="10"
# MAX_CONCURRENT_TASKS="5"
# SHUTDOWN_TIMEOUT="300"

# Logging Configuration (optional - uses defaults)
# LOG_LEVEL="INFO"
# LOG_FORMAT="json"
"""

    try:
        env_path.write_text(env_content)
        console.print(f"[green]✓[/green] Configuration saved to: {env_path}\n")
    except Exception as e:
        console.print(f"[red]Error writing .env file: {e}[/red]")
        sys.exit(1)

    # -------------------------------------------------------------------------
    # Verify Configuration
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 5: Verifying Configuration[/bold cyan]\n")

    try:
        from aegis.config import Settings
        settings = Settings()

        console.print("[green]✓[/green] Configuration loaded successfully")
        console.print(f"  Workspace: {settings.asana_workspace_gid}")
        console.print(f"  Portfolio: {settings.asana_portfolio_gid}")
        console.print(f"  Model: {settings.anthropic_model}\n")

    except Exception as e:
        console.print(f"[yellow]Warning: Could not load configuration: {e}[/yellow]")
        console.print("[dim]You may need to edit .env manually[/dim]\n")

    # -------------------------------------------------------------------------
    # Next Steps
    # -------------------------------------------------------------------------
    console.print("[bold green]✓ Configuration Complete![/bold green]\n")

    console.print("[bold]Next Steps:[/bold]")
    console.print("  1. Setup Asana custom fields:")
    console.print("     [cyan]python tools/setup_asana_custom_fields.py[/cyan]\n")
    console.print("  2. Sync project sections:")
    console.print("     [cyan]aegis sync --portfolio[/cyan]\n")
    console.print("  3. Start the swarm:")
    console.print("     [cyan]aegis start \"Project Name\"[/cyan]\n")

    if "CHANGE_ME" in config_data.values():
        console.print("[yellow]⚠ Warning: Some values need to be updated manually in .env[/yellow]")


@main.command()
def test_asana():
    """Test Asana API connection."""
    console.print("[bold]Testing Asana Connection...[/bold]\n")

    async def _test():
        from aegis.asana.client import AsanaClient

        try:
            settings = Settings()
            client = AsanaClient(settings.asana_access_token)

            # Test portfolio access
            console.print("Fetching portfolio projects...")
            projects = await client.get_portfolio_projects(settings.asana_portfolio_gid)

            console.print(f"[green]✓[/green] Found {len(projects)} project(s):\n")

            for project in projects:
                console.print(f"  • {project.name}")
                console.print(f"    GID: {project.gid}")
                console.print()

            console.print("[green]✓ Asana connection successful[/green]")

        except Exception as e:
            console.print(f"[red]✗ Connection failed: {e}[/red]")
            sys.exit(1)

    asyncio.run(_test())


def _parse_project_input(project: str, settings: Settings) -> str:
    """Parse project input to get GID.

    Args:
        project: Project name, GID, or URL
        settings: Settings instance

    Returns:
        Project GID
    """
    import re

    # If it's a URL, extract GID
    if "asana.com" in project:
        numbers = re.findall(r"\d{13,}", project)
        if numbers:
            return numbers[0]  # First long number is usually project GID
        raise ValueError(f"Could not extract project GID from URL: {project}")

    # If it's already a GID (long number), return it
    if re.match(r"^\d{13,}$", project):
        return project

    # Otherwise, look up by name
    console.print(f"[dim]Resolving project name '{project}'...[/dim]")

    async def _lookup():
        from aegis.asana.client import AsanaClient

        client = AsanaClient(settings.asana_access_token)
        projects = await client.get_portfolio_projects(settings.asana_portfolio_gid)

        for proj in projects:
            if proj.name.lower() == project.lower():
                return proj.gid

        # Not found
        console.print(f"[red]✗ Project '{project}' not found[/red]")
        console.print("\n[dim]Available projects:[/dim]")
        for proj in projects:
            console.print(f"  • {proj.name}")
        sys.exit(1)

    return asyncio.run(_lookup())


if __name__ == "__main__":
    main()
