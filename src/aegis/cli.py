"""New Aegis CLI with SwarmDispatcher integration."""

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import click
import structlog
import logging
from datetime import datetime
from rich.console import Console
import asana
import urllib.request
import webbrowser
import tempfile
import os

from aegis.config import Settings, get_settings
from aegis.infrastructure.pid_manager import PIDLockError, PIDManager
from aegis.asana.client import AsanaClient
from aegis.orchestrator.dispatcher import SwarmDispatcher
from aegis.infrastructure.asana_service import AsanaService
from aegis.infrastructure.memory_manager import MemoryManager
from aegis.infrastructure.worktree_manager import WorktreeManager
from aegis.core.tracker import ProjectTracker
from aegis.agents import (
    DocumentationAgent,
    MergerAgent,
    PlannerAgent,
    ReviewerAgent,
    TriageAgent,
    WorkerAgent,
)
from aegis.utils.asana_utils import format_asana_resource

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
@click.argument("project", required=False)
@click.option("--no-dashboard", is_flag=True, help="Don't start the dashboard")
def start(project: str | None, no_dashboard: bool):
    """Start the Aegis Master Process.

    If PROJECT is provided, it will be tracked (if not already) before starting.
    PROJECT can be a project name, GID, or Asana URL.

    Examples:
        aegis start
        aegis start Aegis
    """
    from aegis.config import get_settings
    settings = get_settings()

    # If project provided, ensure it's tracked
    if project:
        # TODO: Implement tracking logic if needed
        pass

    if not no_dashboard:
        # Start dashboard in background
        dashboard_port = 8501
        console.print(f"[green]Starting dashboard at http://localhost:{dashboard_port}[/green]")
        subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", "src/aegis/dashboard/app.py", "--server.port", str(dashboard_port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    console.print("[bold green]Starting Aegis Master Process...[/bold green]")

    from aegis.orchestrator.master import MasterProcess

    master = MasterProcess()
    try:
        asyncio.run(master.start())
    except KeyboardInterrupt:
        # Master handles signals, but just in case
        pass
    except Exception as e:
        console.print(f"[bold red]Master Process failed:[/bold red] {e}")
        sys.exit(1)



@main.command(name="agent")
@click.argument("agent_name", required=False)
@click.argument("task_id", required=False)
@click.option("--interactive", is_flag=True, help="Run in interactive mode (inherit stdio)")
def agent_command(agent_name: str | None, task_id: str | None, interactive: bool):
    """Manage and run Aegis agents.

    If no arguments are provided, lists available agents.

    To run an agent:
        aegis agent <AGENT_NAME> <TASK_ID>

    Example:
        aegis agent triage 1234567890
    """
    from aegis.agents import __all__ as available_agents
    from aegis.agents import (
        ConsolidatorAgent,
        DocumentationAgent,
        IdeationAgent,
        MergerAgent,
        PlannerAgent,
        RefactorAgent,
        ReviewerAgent,
        TriageAgent,
        WorkerAgent,
    )
    from aegis.agents.base import AgentTargetType
    from aegis.asana.models import AsanaProject, AsanaTask
    from rich.prompt import Prompt

    # Map class names to classes for docstring access and instantiation
    agent_classes = {
        "ConsolidatorAgent": ConsolidatorAgent,
        "DocumentationAgent": DocumentationAgent,
        "IdeationAgent": IdeationAgent,
        "MergerAgent": MergerAgent,
        "PlannerAgent": PlannerAgent,
        "RefactorAgent": RefactorAgent,
        "ReviewerAgent": ReviewerAgent,
        "TriageAgent": TriageAgent,
        "WorkerAgent": WorkerAgent,
    }

    # Handle "list" command explicitly or empty agent_name
    if not agent_name or agent_name.lower() == "list":
        console.print("[bold]Available Agents:[/bold]\n")

        for agent_class_name in available_agents:
            if agent_class_name in ["AgentResult", "BaseAgent"]:
                continue

            agent_cls = agent_classes.get(agent_class_name)
            description = "No description available."
            if agent_cls and agent_cls.__doc__:
                # Take the first line of the docstring
                description = agent_cls.__doc__.strip().split('\n')[0]

            # Convert CamelCase to readable name if needed, or just use class name
            display_name = agent_class_name.replace("Agent", "")
            agent_name_property = None

            # Get target type if possible
            target_info = ""
            try:
                # Create minimal mocks to instantiate
                from unittest.mock import MagicMock
                mock_service = MagicMock()
                mock_repo = Path("/tmp")
                mock_worktree = MagicMock()
                mock_memory = MagicMock()

                if agent_class_name in ["WorkerAgent", "ReviewerAgent", "MergerAgent"]:
                    instance = agent_cls(mock_service, mock_repo, worktree_manager=mock_worktree)
                elif agent_class_name == "DocumentationAgent":
                    instance = agent_cls(mock_service, mock_repo, memory_manager=mock_memory)
                else:
                    # Triage, Planner, Ideation, Consolidator, Refactor
                    instance = agent_cls(mock_service, mock_repo)

                target_info = f" [dim]({instance.target_type.value})[/dim]"
                agent_name_property = instance.name
            except Exception:
                target_info = ""

            if agent_name_property:
                display_name = agent_name_property

            console.print(f"[green]• {display_name}[/green]{target_info}")
            console.print(f"  {description}\n")
        return

    # Run Agent Logic

    async def _run_agent():
        try:
            settings = get_settings()
            client = AsanaClient(settings.asana_access_token)
            asana_service = AsanaService(client)
            repo_root = Path.cwd()

            # 1. Resolve Agent Class
            name_lower = agent_name.lower()
            target_class_name = None
            for cls_name in agent_classes.keys():
                if cls_name.lower().replace("agent", "") == name_lower:
                    target_class_name = cls_name
                    break
                # Handle snake_case input (e.g. triage_agent -> TriageAgent)
                if cls_name.lower() == name_lower.replace("_", ""):
                    target_class_name = cls_name
                    break

            if not target_class_name:
                for cls_name in agent_classes.keys():
                    if cls_name.lower() == name_lower:
                        target_class_name = cls_name
                        break

            if not target_class_name:
                console.print(f"[red]✗ Unknown agent: {agent_name}[/red]")
                sys.exit(1)

            agent_cls = agent_classes[target_class_name]

            # 2. Instantiate Agent
            # We need to instantiate to check target_type and execute
            try:
                if target_class_name in ["WorkerAgent", "ReviewerAgent", "MergerAgent"]:
                    worktree_manager = WorktreeManager(repo_root)
                    agent_instance = agent_cls(asana_service, repo_root, worktree_manager=worktree_manager)
                elif target_class_name == "DocumentationAgent":
                    memory_manager = MemoryManager(repo_root)
                    agent_instance = agent_cls(asana_service, repo_root, memory_manager=memory_manager)
                else:
                    # Triage, Planner, Ideation, Consolidator, Refactor
                    agent_instance = agent_cls(asana_service, repo_root)
            except Exception as e:
                console.print(f"[red]Error instantiating agent: {e}[/red]")
                sys.exit(1)

            # 3. Resolve Target
            target = None
            target_gid = task_id

            if not target_gid:
                # Interactive Selection
                console.print(f"[bold]Select target for {agent_instance.name} ({agent_instance.target_type.value})...[/bold]")

                # Fetch Portfolio Projects
                if not settings.asana_portfolio_gid:
                    console.print("[red]ASANA_PORTFOLIO_GID not set. Cannot list projects.[/red]")
                    sys.exit(1)

                console.print("[dim]Fetching projects...[/dim]")
                projects = await client.get_portfolio_projects(settings.asana_portfolio_gid)

                if not projects:
                    console.print("[yellow]No projects found in portfolio.[/yellow]")
                    sys.exit(1)

                # Select Project
                console.print("\n[bold]Available Projects:[/bold]")
                for idx, p in enumerate(projects):
                    console.print(f"  {idx + 1}. {p.name}")

                choice = Prompt.ask("Select project", choices=[str(i+1) for i in range(len(projects))], default="1")
                selected_project = projects[int(choice) - 1]

                if agent_instance.target_type == AgentTargetType.PROJECT:
                    target = selected_project
                    target_gid = target.gid
                else:
                    # Task Target - Select Task in Project
                    console.print(f"\n[dim]Fetching tasks for {selected_project.name}...[/dim]")

                    # Get sections to help filter? Or just all tasks?
                    # Let's get tasks grouped by section
                    sections = await client.get_project_sections(selected_project.gid)

                    # We want to let user pick a section first to narrow down
                    console.print("\n[bold]Sections:[/bold]")
                    for idx, s in enumerate(sections):
                        console.print(f"  {idx + 1}. {s.name}")

                    s_choice = Prompt.ask("Select section", choices=[str(i+1) for i in range(len(sections))], default="1")
                    selected_section = sections[int(s_choice) - 1]

                    tasks = await client.get_tasks_in_section(selected_section.gid)

                    if not tasks:
                        console.print(f"[yellow]No tasks found in {selected_section.name}.[/yellow]")
                        sys.exit(1)

                    console.print(f"\n[bold]Tasks in {selected_section.name}:[/bold]")
                    for idx, t in enumerate(tasks):
                        console.print(f"  {idx + 1}. {t.name}")

                    t_choice = Prompt.ask("Select task", choices=[str(i+1) for i in range(len(tasks))], default="1")
                    target_gid = tasks[int(t_choice) - 1].gid

            # 4. Fetch Full Target Details
            if not target:
                if agent_instance.target_type == AgentTargetType.PROJECT:
                    # We need to fetch full project details if we only have GID?
                    # AsanaService doesn't have get_project? It has client.get_project
                    # But execute expects AsanaProject model.
                    # Let's check AsanaService.
                    # It seems AsanaService wraps client.
                    # Let's use client directly if needed or add to service.
                    # client.get_project returns AsanaProject.
                    target = await client.get_project(target_gid)
                else:
                    target = await asana_service.get_task(target_gid)

            console.print(f"[green]✓[/green] Target: {format_asana_resource(target)}\n")

            # 5. Execute Agent
            console.print(f"[bold green]Running {agent_instance.name}...[/bold green]")
            if interactive:
                console.print("[dim]Entering interactive mode...[/dim]\n")

            result = await agent_instance.execute(target, interactive=interactive)

            if result.success:
                console.print(f"\n[green]✓ Execution successful[/green]")
                console.print(f"Summary: {result.summary}")
                if result.details:
                    console.print("Details:")
                    for detail in result.details:
                        console.print(f"  • {detail}")
            else:
                console.print(f"\n[red]✗ Execution failed[/red]")
                console.print(f"Error: {result.error}")
                sys.exit(1)

        except Exception as e:
            console.print(f"[red]Fatal error: {e}[/red]")
            # import traceback
            # traceback.print_exc()
            sys.exit(1)

    try:
        asyncio.run(_run_agent())
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)


@main.command()
@click.argument("project", required=False)
def stop(project: str | None):
    """Stop a running swarm dispatcher.

    If PROJECT is provided, stops the dispatcher for that project.
    If PROJECT is not provided, attempts to stop the dispatcher for the current directory's project.
    """
    console.print("[bold]Stopping Aegis Swarm...[/bold]")

    try:
        project_gid = None
        settings = get_settings()
        tracker = ProjectTracker()

        async def _resolve_project():
            if project:
                # Resolve GID from input
                gid = await _parse_project_input(project, settings)

                # Try to find in tracker
                tracked = tracker.get_project(gid)
                if tracked:
                    return gid, Path(tracked["local_path"])

                # Not tracked. Assume CWD.
                return gid, Path.cwd()
            else:
                # Try to infer from CWD
                cwd = Path.cwd()
                tracked = tracker.find_by_path(cwd)
                if tracked:
                    return tracked["gid"], Path(tracked["local_path"])
                else:
                    # Fallback to legacy behavior (local .aegis.pid)
                    if Path(".aegis.pid").exists():
                        return None, cwd # Use default legacy

                    # Check for any .aegis/pids/*.pid in CWD
                    pids_dir = cwd / ".aegis" / "pids"
                    if pids_dir.exists():
                        pids = list(pids_dir.glob("*.pid"))
                        if len(pids) == 1:
                            return pids[0].stem, cwd
                        elif len(pids) > 1:
                             console.print("[red]Multiple projects running in this directory. Please specify one.[/red]")
                             sys.exit(1)

                    console.print("[red]Error: Could not determine project to stop.[/red]")
                    console.print("Please specify a project or run from a tracked project directory.")
                    sys.exit(1)

        project_gid, project_path = asyncio.run(_resolve_project())

        pid_manager = PIDManager(project_gid=project_gid, root_dir=project_path)

        if pid_manager.stop_orchestrator(timeout=60):
            target = f" ({project_gid})" if project_gid else ""
            console.print(f"[green]✓[/green] Dispatcher stopped successfully{target}")
        else:
            console.print("[yellow]No dispatcher is currently running[/yellow]")

    except Exception as e:
        console.print(f"[red]Error stopping dispatcher: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("project", required=False)
def status(project: str | None):
    """Show dispatcher status.

    If PROJECT is provided, shows status for that project.
    If PROJECT is not provided, shows status for current directory's project (if tracked) or all tracked projects.
    """
    console.print("[bold]Aegis Swarm Status[/bold]\n")

    try:
        settings = get_settings()
        tracker = ProjectTracker()

        projects_to_check = []

        async def _get_projects_to_check():
            projects = []
            if project:
                 # Specific project
                gid = await _parse_project_input(project, settings)
                tracked = tracker.get_project(gid)
                if tracked:
                    projects.append(tracked)
                else:
                    # Not tracked, but maybe we can still check status if we have GID
                    projects.append({
                        "gid": gid,
                        "name": project, # We might not know the real name yet
                        "local_path": str(Path.cwd()) # Assume current dir?
                    })
            else:
                # All tracked projects
                projects = tracker.get_projects()

                # Also check for any running PIDs in local .aegis/pids that might not be tracked
                local_pids_dir = Path.cwd() / ".aegis" / "pids"
                if local_pids_dir.exists():
                    for pid_file in local_pids_dir.glob("*.pid"):
                        gid = pid_file.stem
                        # If not already in projects_to_check
                        if not any(p["gid"] == gid for p in projects):
                            projects.append({
                                "gid": gid,
                                "name": f"Untracked ({gid})",
                                "local_path": str(Path.cwd()) # Best guess
                            })
            return projects

        projects_to_check = asyncio.run(_get_projects_to_check())

        if not projects_to_check:
            console.print("[yellow]No projects found.[/yellow]")
            console.print("Use 'aegis track' to track a project or 'aegis start' to start one.")
            return

        for p in projects_to_check:
            gid = p["gid"]
            name = p["name"]

            # Try to get real name if it's "Untracked"
            if name.startswith("Untracked"):
                try:
                    # Quick lookup if we have a client
                    client = AsanaClient(settings.asana_access_token)
                    # This might be slow for many projects, but okay for status
                    # We can't easily await here without making status async?
                    # Or just show GID.
                    pass
                except:
                    pass

            pid_manager = PIDManager(project_gid=gid, root_dir=p["local_path"])
            pid = pid_manager.get_running_pid()

            if pid:
                display_name = f"{name} ({gid})"
                if name.startswith("Untracked"):
                     display_name = name

                console.print(f"[green]● {display_name}[/green]")
                console.print(f"  PID: {pid}")
                console.print(f"  Path: {p['local_path']}")

                # Get state
                try:
                    state_file = Path(p["local_path"]) / ".aegis" / "swarm_state.json"
                    if state_file.exists():
                        with open(state_file) as f:
                            state = json.load(f)

                        # The state file structure changed, it's not directly active_tasks anymore
                        # It's under 'orchestrator' key
                        orch_state = state.get("orchestrator", {})
                        active_tasks = orch_state.get("active_tasks", [])

                        console.print(f"  Started: {orch_state.get('started_at', 'Unknown')}")
                        console.print(f"  Last Poll: {orch_state.get('last_poll', 'Unknown')}")
                        console.print(f"  Active Tasks: {len(active_tasks)}")

                        if active_tasks:
                            console.print("  Tasks:")
                            for task_gid in active_tasks:
                                console.print(f"    • {task_gid}")
                except Exception:
                    console.print("  [dim]Could not read state file[/dim]")
                console.print("")
            else:
                # Show not running status for all tracked projects
                console.print(f"[dim]○ {name} ({gid}): Not running[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("arg1", required=False)
@click.argument("arg2", required=False)
@click.option("--remove", is_flag=True, help="Remove a tracked project")
def track(arg1: str | None, arg2: str | None, remove: bool):
    """Track or untrack a project for syncing.

    To track a new project:
        aegis track <ASANA_URI> <LOCAL_PATH>

    To remove a tracked project:
        aegis track --remove <ASANA_URI_OR_GID>
        aegis track --remove <LOCAL_PATH>
    """
    try:
        tracker = ProjectTracker()

        async def _track_project():
            settings = get_settings()

            if remove:
                # Removal Mode
                target = arg1
                project_to_remove = None

                # Try to find by GID/URI first
                try:
                    # Check if it looks like a GID or URL
                    if "asana.com" in target or target.isdigit():
                        gid = await _parse_project_input(target, settings)
                        project_to_remove = tracker.get_project(gid)
                except Exception:
                    pass

                # If not found, try by path
                if not project_to_remove:
                    # Resolve path
                    try:
                        path = Path(target).resolve()
                        project_to_remove = tracker.find_by_path(path)
                    except Exception:
                        pass

                if not project_to_remove:
                    console.print(f"[red]Error: No tracked project found matching '{target}'[/red]")
                    sys.exit(1)

                # Confirm removal
                console.print(f"[bold]Found project:[/bold] {project_to_remove['name']}")
                console.print(f"  GID: {project_to_remove['gid']}")
                console.print(f"  Path: {project_to_remove['local_path']}")

                if click.confirm("\nAre you sure you want to stop tracking this project?", default=False):
                    tracker.remove_project(project_to_remove['gid'])
                    console.print("[green]✓[/green] Project removed from tracking.")
                else:
                    console.print("[dim]Operation cancelled.[/dim]")

            else:
                # Add Mode
                if not arg1 or not arg2:
                    console.print("[red]Error: To track a project, provide both ASANA_URI and LOCAL_PATH.[/red]")
                    console.print("Usage: aegis track <ASANA_URI> <LOCAL_PATH>")
                    sys.exit(1)

                asana_uri = arg1
                local_path = arg2

                project_gid = await _parse_project_input(asana_uri, settings)

                # Get project name from Asana
                client = AsanaClient(settings.asana_access_token)
                console.print("[dim]Fetching project details...[/dim]")
                project = await client.get_project(project_gid)
                project_name = project.name

                # Resolve path
                resolved_path = Path(local_path).resolve()
                if not resolved_path.exists():
                        console.print(f"[yellow]Warning: Path {resolved_path} does not exist.[/yellow]")
                        if not click.confirm("Track anyway?", default=False):
                            sys.exit(1)

                tracker.add_project(project_gid, project_name, resolved_path)

                console.print(f"[green]✓[/green] Now tracking project: [bold]{project_name}[/bold]")
                console.print(f"  GID: {project_gid}")
                console.print(f"  Path: {resolved_path}")

        asyncio.run(_track_project())

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@main.command()
@click.argument("project", required=False)
@click.option("--portfolio", required=False, is_flag=False, flag_value="default", help="Sync all projects in portfolio (uses default if no ID provided)")
@click.option("--dry-run", is_flag=True, help="Show what would change without applying")
def sync(project: str | None, portfolio: str | None, dry_run: bool):
    """Sync Asana project sections to canonical structure.

    Ensures projects have the correct sections in the right order.

    If no arguments are provided, syncs all tracked projects.

    Examples:
        aegis sync --project Aegis
        aegis sync --portfolio          # Uses portfolio from .env
        aegis sync --portfolio <GID>    # Uses specified portfolio
        aegis sync                      # Syncs all tracked projects
    """
    console.print("[bold]Syncing Asana Sections...[/bold]\n")

    try:
        # Build command
        cmd = ["python", "tools/sync_asana_project.py"]
        settings = get_settings()

        if project:
            project_gid = asyncio.run(_parse_project_input(project, settings))
            cmd.extend(["--project", project_gid])

        elif portfolio:
            target_portfolio = portfolio
            if portfolio == "default":
                if not settings.asana_portfolio_gid:
                    console.print("[red]Error: No default portfolio configured in settings.[/red]")
                    sys.exit(1)
                target_portfolio = settings.asana_portfolio_gid

            cmd.extend(["--portfolio", target_portfolio])

        else:
            # No args - sync tracked projects
            tracker = ProjectTracker()
            tracked_projects = tracker.get_projects()

            if not tracked_projects:
                console.print("[yellow]No tracked projects found.[/yellow]")
                console.print("Use [bold]aegis track <ASANA_URI> <PATH>[/bold] to track a project.")
                console.print("Or specify --project or --portfolio.")
                sys.exit(0)

            console.print(f"[dim]Found {len(tracked_projects)} tracked project(s)[/dim]")
            for p in tracked_projects:
                cmd.extend(["--project", p["gid"]])

        if dry_run:
            cmd.append("--dry-run")

        # Prepare environment
        env = os.environ.copy()
        env.update({
            "ASANA_ACCESS_TOKEN": settings.asana_access_token,
            "ASANA_WORKSPACE_GID": settings.asana_workspace_gid,
            "ASANA_PORTFOLIO_GID": settings.asana_portfolio_gid,
            "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        })
        if settings.asana_team_gid:
            env["ASANA_TEAM_GID"] = settings.asana_team_gid

        # Run sync tool
        result = subprocess.run(cmd, cwd=Path.cwd(), env=env)
        sys.exit(result.returncode)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)



@main.command()
def init():
    """Initialize a new Aegis project configuration.

    Creates default configuration files in the current directory:
    - .env (from example)
    - swarm_memory.md
    - user_preferences.md
    - .aegis/ directory
    """
    console.print("[bold]Initializing Aegis Project...[/bold]\n")

    try:
        cwd = Path.cwd()

        # 1. Create .env
        env_file = cwd / ".env"
        if env_file.exists():
            console.print(f"[yellow]! .env already exists at {env_file}[/yellow]")
        else:
            # Try to find example in package or use hardcoded default
            # Since we are installed, we might not have easy access to source .env.example
            # So we'll write a default one.
            default_env = """# Asana Configuration
ASANA_ACCESS_TOKEN=your_asana_personal_access_token_here
ASANA_WORKSPACE_GID=your_workspace_gid
ASANA_PORTFOLIO_GID=your_portfolio_gid
# ASANA_TEAM_GID=your_team_gid  # Optional

# Anthropic Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_MAX_TOKENS=4096

# Database Configuration
DATABASE_URL=postgresql://localhost/aegis
REDIS_URL=redis://localhost:6379

# Orchestrator Configuration
POLL_INTERVAL_SECONDS=30
MAX_CONCURRENT_TASKS=5
LOG_LEVEL=INFO
"""
            with open(env_file, "w") as f:
                f.write(default_env)
            console.print(f"[green]✓[/green] Created .env")

        # 2. Create swarm_memory.md
        memory_file = cwd / "swarm_memory.md"
        if memory_file.exists():
            console.print(f"[yellow]! swarm_memory.md already exists at {memory_file}[/yellow]")
        else:
            default_memory = """# Swarm Memory

This file serves as the global context and long-term memory for the Aegis swarm.
Agents read this file to understand the broader project goals, architectural decisions, and current state.

## Project Overview
[Description of the project]

## Architecture
[High-level architecture description]

## Current Focus
[What is the swarm currently working on?]
"""
            with open(memory_file, "w") as f:
                f.write(default_memory)
            console.print(f"[green]✓[/green] Created swarm_memory.md")

        # 3. Create user_preferences.md
        prefs_file = cwd / "user_preferences.md"
        if prefs_file.exists():
            console.print(f"[yellow]! user_preferences.md already exists at {prefs_file}[/yellow]")
        else:
            default_prefs = """# User Preferences

This file contains your personal preferences and rules for the Aegis swarm.
Agents will respect these guidelines when generating code or making decisions.

## Coding Style
- Prefer explicit over implicit.
- Use type hints everywhere.
- Write docstrings for all public modules, classes, and functions.

## Communication
- Be concise.
- Focus on technical details.
"""
            with open(prefs_file, "w") as f:
                f.write(default_prefs)
            console.print(f"[green]✓[/green] Created user_preferences.md")

        # 4. Create .aegis directory
        aegis_dir = cwd / ".aegis"
        if aegis_dir.exists():
             console.print(f"[yellow]! .aegis directory already exists at {aegis_dir}[/yellow]")
        else:
            aegis_dir.mkdir()
            console.print(f"[green]✓[/green] Created .aegis directory")

        console.print("\n[bold green]Initialization complete![/bold green]")
        console.print("Please edit [bold].env[/bold] to add your API keys and configuration.")

    except Exception as e:
        console.print(f"[red]Error initializing project: {e}[/red]")
        sys.exit(1)



@main.command()
@click.argument("name")
@click.argument("path", required=False)
def create(name: str, path: str | None):
    """Create a new Aegis project.

    NAME: Name of the project (will be created in Asana)
    PATH: Local path to initialize (defaults to current directory)
    """
    console.print(f"[bold]Creating Aegis Project: {name}[/bold]\n")

    try:
        settings = Settings()
        client = AsanaClient(settings.asana_access_token)
        tracker = ProjectTracker()

        # 1. Resolve Path
        if path:
            project_path = Path(path).resolve()
            if not project_path.exists():
                console.print(f"[dim]Creating directory {project_path}...[/dim]")
                project_path.mkdir(parents=True)
        else:
            project_path = Path.cwd()

        console.print(f"[dim]Local path: {project_path}[/dim]")

        # 2. Create Asana Project
        console.print("[dim]Creating project in Asana...[/dim]")

        # Determine team GID (required for organizations)
        team_gid = settings.asana_team_gid
        if not team_gid:
             # Try to find a team or warn?
             # For now, let's assume workspace is enough or user provided team_gid in env
             pass

        async def _create_project_flow():
            # Create project
            project = await client.create_project(
                workspace_gid=settings.asana_workspace_gid,
                name=name,
                notes="Managed by Aegis Swarm",
                team_gid=team_gid
            )
            console.print(f"[green]✓[/green] Created project {project.name} ({project.gid})")

            # Add to portfolio if configured
            if settings.asana_portfolio_gid:
                try:
                    await client.add_project_to_portfolio(settings.asana_portfolio_gid, project.gid)
                    console.print(f"[green]✓[/green] Added to portfolio {settings.asana_portfolio_gid}")
                except Exception as e:
                    console.print(f"[yellow]Warning: Failed to add to portfolio: {e}[/yellow]")

            # 3. Add Custom Fields
            console.print("[dim]Adding custom fields...[/dim]")

            # Load schema
            schema_path = Path(__file__).parent.parent.parent / "schema" / "asana_config.json"
            if schema_path.exists():
                with open(schema_path) as f:
                    schema = json.load(f)

                required_fields = schema.get("custom_fields", [])

                # Get workspace fields to find GIDs
                # We need to use the low-level API or add a method to client
                # For now, let's use the client's internal API client if accessible or add a method
                # Client has `custom_fields_api`

                # We'll implement a quick lookup here using the client's api_client
                # Ideally this should be in AsanaClient, but for speed we do it here or use a helper
                # Actually, let's use the helper from tools/setup_asana_custom_fields.py logic
                # But we can't import it easily.
                # Let's use the client.api_client

                custom_fields_api = asana.CustomFieldsApi(client.api_client)
                workspace_fields = await asyncio.to_thread(
                    custom_fields_api.get_custom_fields_for_workspace,
                    settings.asana_workspace_gid,
                    {"opt_fields": "name,gid"}
                )

                workspace_field_map = {f["name"]: f["gid"] for f in workspace_fields}

                added_count = 0
                for field_def in required_fields:
                    fname = field_def["name"]
                    if fname in workspace_field_map:
                        fgid = workspace_field_map[fname]
                        try:
                            await client.add_custom_field_to_project(project.gid, fgid)
                            added_count += 1
                        except Exception as e:
                            console.print(f"[yellow]  ! Failed to add {fname}: {e}[/yellow]")
                    else:
                        console.print(f"[yellow]  ! Custom field '{fname}' not found in workspace. Run 'python tools/setup_asana_custom_fields.py'[/yellow]")

                console.print(f"[green]✓[/green] Added {added_count} custom fields")
            else:
                console.print("[yellow]Warning: Schema file not found, skipping custom fields.[/yellow]")

            return project

        project = asyncio.run(_create_project_flow())

        # 4. Sync Sections
        console.print("[dim]Syncing sections...[/dim]")
        tools_path = Path(__file__).parent.parent.parent / "tools"
        sync_tool = tools_path / "sync_asana_project.py"

        if sync_tool.exists():
             env = os.environ.copy()
             env.update({
                "ASANA_ACCESS_TOKEN": settings.asana_access_token,
                "ASANA_WORKSPACE_GID": settings.asana_workspace_gid,
                "ASANA_PORTFOLIO_GID": settings.asana_portfolio_gid,
                "ANTHROPIC_API_KEY": settings.anthropic_api_key,
            })
             if settings.asana_team_gid:
                env["ASANA_TEAM_GID"] = settings.asana_team_gid

             try:
                subprocess.run(
                    ["python", str(sync_tool), "--project", project.gid],
                    cwd=Path.cwd(),
                    env=env,
                    check=True,
                    capture_output=True
                )
                console.print(f"[green]✓[/green] Synced sections")
             except subprocess.CalledProcessError as e:
                console.print(f"[yellow]Warning: Failed to sync sections: {e}[/yellow]")
        else:
             console.print(f"[yellow]Warning: Sync tool not found at {sync_tool}[/yellow]")

        # 5. Track Project
        tracker.add_project(project.gid, name, project_path)
        console.print(f"[green]✓[/green] Tracked project locally")

        # 6. Initialize Local Files (Init)
        # We can call the init function logic, but since it's a click command, it's harder to invoke directly without context.
        # We'll just replicate the logic or call it via subprocess?
        # Replicating is safer and cleaner here.

        console.print("[dim]Initializing local files...[/dim]")

        # .env
        env_file = project_path / ".env"
        if not env_file.exists():
            # Copy from current env or example?
            # If we are creating a new project, we probably want to copy the current .env if it exists
            # or create a new one.
            # Let's assume we want to copy the current configuration since we are running with it.

            current_env = Path.cwd() / ".env"
            if current_env.exists():
                import shutil
                shutil.copy(current_env, env_file)
                console.print(f"[green]✓[/green] Copied .env from current directory")
            else:
                # Write default
                default_env = """# Asana Configuration
ASANA_ACCESS_TOKEN=your_asana_personal_access_token_here
ASANA_WORKSPACE_GID=your_workspace_gid
ASANA_PORTFOLIO_GID=your_portfolio_gid

# Anthropic Configuration
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_MAX_TOKENS=4096

# Database Configuration
DATABASE_URL=postgresql://localhost/aegis
REDIS_URL=redis://localhost:6379

# Orchestrator Configuration
POLL_INTERVAL_SECONDS=30
MAX_CONCURRENT_TASKS=5
LOG_LEVEL=INFO
"""
                with open(env_file, "w") as f:
                    f.write(default_env)
                console.print(f"[green]✓[/green] Created .env")

        # swarm_memory.md
        memory_file = project_path / "swarm_memory.md"
        if not memory_file.exists():
            default_memory = f"""# Swarm Memory - {name}

This file serves as the global context and long-term memory for the Aegis swarm.

## Project Overview
{name} is a new project managed by Aegis.

## Architecture
[High-level architecture description]

## Current Focus
Initial setup and planning.
"""
            with open(memory_file, "w") as f:
                f.write(default_memory)
            console.print(f"[green]✓[/green] Created swarm_memory.md")

        # user_preferences.md
        prefs_file = project_path / "user_preferences.md"
        if not prefs_file.exists():
            default_prefs = """# User Preferences

## Coding Style
- Prefer explicit over implicit.
- Use type hints everywhere.

## Communication
- Be concise.
"""
            with open(prefs_file, "w") as f:
                f.write(default_prefs)
            console.print(f"[green]✓[/green] Created user_preferences.md")

        # .aegis directory
        aegis_dir = project_path / ".aegis"
        aegis_dir.mkdir(exist_ok=True)
        console.print(f"[green]✓[/green] Created .aegis directory")

        console.print(f"\n[bold green]Project {name} created successfully![/bold green]")
        console.print(f"Location: {project_path}")
        console.print(f"Asana: https://app.asana.com/0/{project.gid}/list")

    except Exception as e:
        console.print(f"[red]Error creating project: {e}[/red]")
        sys.exit(1)


@main.group()
def dashboard():
    """Manage the Aegis Dashboard."""
    pass


@dashboard.command()
@click.option("--port", default=8501, help="Port to run the dashboard on")
def start(port: int):
    """Start the Aegis Dashboard in the background.

    Starts a Streamlit application to visualize the swarm state, logs, and active tasks.
    """
    console.print(f"[bold green]Starting Aegis Dashboard on port {port}...[/bold green]")

    dashboard_path = Path(__file__).parent / "dashboard" / "app.py"
    if not dashboard_path.exists():
        console.print(f"[red]Error: Dashboard application not found at {dashboard_path}[/red]")
        sys.exit(1)

    # Check if already running
    pid_file = Path.cwd() / ".aegis" / "dashboard_pid"
    pid_manager = PIDManager(pid_file=pid_file)

    try:
        pid_manager.acquire()
    except PIDLockError:
        console.print(f"[yellow]! Dashboard is already running (PID file: {pid_file}).[/yellow]")
        console.print("Use 'aegis dashboard stop' to stop it first.")
        sys.exit(1)

    try:
        # Start in background
        log_file = Path.cwd() / ".aegis" / "dashboard.log"
        with open(log_file, "w") as f:
            process = subprocess.Popen(
                ["streamlit", "run", str(dashboard_path), "--server.port", str(port)],
                stdout=f,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )

        # Update PID file with the actual process PID (since acquire() wrote our PID)
        # Wait, acquire() writes the current process PID. But we want the subprocess PID.
        # Actually, we should probably let the subprocess manage its own PID or just write the subprocess PID here.
        # PIDManager.acquire() writes os.getpid().
        # We need to manually overwrite it with the subprocess PID.

        with open(pid_file, "w") as f:
            f.write(str(process.pid))

        console.print(f"[green]✓[/green] Dashboard started in background (PID: {process.pid})")
        console.print(f"[dim]Logs: {log_file}[/dim]")

        # We don't release the lock here because the background process is now "holding" it (conceptually)
        # But PIDManager is designed for the current process.
        # Since we are exiting, we shouldn't call release().
        # However, PIDManager.__exit__ or destructor might not be called if we just exit?
        # Actually, we instantiated PIDManager, called acquire().
        # If we exit, the file remains. That's what we want.

    except FileNotFoundError:
        console.print("[red]Error: 'streamlit' not found. Please run 'uv sync' to install dependencies.[/red]")
        # Clean up PID file since we failed to start
        pid_manager.release()
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error starting dashboard: {e}[/red]")
        pid_manager.release()
        sys.exit(1)


@dashboard.command()
def stop():
    """Stop the running Aegis Dashboard."""
    console.print("[bold]Stopping Aegis Dashboard...[/bold]")

    pid_file = Path.cwd() / ".aegis" / "dashboard_pid"
    pid_manager = PIDManager(pid_file=pid_file)

    if pid_manager.stop_orchestrator(timeout=10):
        console.print("[green]✓[/green] Dashboard stopped successfully")
    else:
        console.print("[yellow]No dashboard is currently running[/yellow]")
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
@click.option("--show", is_flag=True, help="Display current configuration")
def configure(show: bool):
    """Interactive configuration wizard.

    Walks you through setting up Aegis by collecting:
    - Asana Personal Access Token
    - Asana Workspace, Team, and Portfolio GIDs
    - Anthropic API Key

    Opens browser tabs to help you get the required tokens.
    """
    if show:
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
            return

        except Exception as e:
            console.print(f"[red]Error loading configuration: {e}[/red]")
            console.print("\n[dim]Make sure .env file exists with required variables[/dim]")
            sys.exit(1)
    from dotenv import dotenv_values

    console.print("[bold green]Aegis Configuration Wizard[/bold green]\n")
    console.print("This wizard will help you set up Aegis by collecting necessary credentials.\n")

    env_path = Path.cwd() / ".env"
    existing_config = {}

    # Check if .env exists and load values
    if env_path.exists():
        console.print(f"[dim]Loading defaults from {env_path}...[/dim]\n")
        existing_config = dotenv_values(env_path)

    # Collect configuration
    config_data = {}
    config_names = {}  # Store names for summary

    # -------------------------------------------------------------------------
    # Asana Configuration
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 1: Asana Configuration[/bold cyan]\n")

    console.print("You'll need an Asana Personal Access Token.")
    console.print("[dim]This allows Aegis to read and update tasks in your Asana workspace.[/dim]\n")

    default_token = existing_config.get("ASANA_ACCESS_TOKEN")

    if not default_token:
        if click.confirm("Open Asana Personal Access Token page in browser?", default=True):
            webbrowser.open("https://app.asana.com/0/my-apps")
            console.print("[green]✓[/green] Opened in browser\n")

        console.print("Steps to get your token:")
        console.print("  1. Go to Asana → Profile Icon → My Settings")
        console.print("  2. Click 'Apps' tab")
        console.print("  3. Click 'Create new token'")
        console.print("  4. Name it 'Aegis' and click 'Create token'")
        console.print("  5. Copy the token (it starts with '1/')\n")
    else:
        # Create masked default for display
        masked_default = f"...{default_token[-4:]}" if len(default_token) > 4 else default_token

    asana_token = click.prompt(
        "Paste your Asana Personal Access Token",
        type=str,
        default=default_token,
        show_default=masked_default if default_token else True,
    )
    config_data["ASANA_ACCESS_TOKEN"] = asana_token.strip()

    console.print("\n[dim]Testing Asana connection...[/dim]")

    # Test Asana connection and get workspace info
    try:
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
            # Only one workspace, auto-select but confirm
            workspace = workspaces_list[0]
            workspace_dict = workspace if isinstance(workspace, dict) else workspace.to_dict()
            console.print(f"[green]✓[/green] Found workspace: {workspace_dict['name']}")

            if not click.confirm("Use this workspace?", default=True):
                console.print("[yellow]Only one workspace found. To use another, please check your Asana permissions.[/yellow]")
                sys.exit(1)

            config_data["ASANA_WORKSPACE_GID"] = workspace_dict["gid"]
            config_names["ASANA_WORKSPACE_GID"] = workspace_dict["name"]
            workspace_gid = workspace_dict["gid"]
            is_org = workspace_dict.get("is_organization", False)
        else:
            # Multiple workspaces, let user choose
            console.print("Found multiple workspaces:\n")

            default_workspace_idx = 1
            current_gid = existing_config.get("ASANA_WORKSPACE_GID")

            for i, ws in enumerate(workspaces_list, 1):
                ws_dict = ws if isinstance(ws, dict) else ws.to_dict()
                marker = ""
                if current_gid and ws_dict["gid"] == current_gid:
                    marker = " [bold green](Current)[/bold green]"
                    default_workspace_idx = i
                console.print(f"  {i}. {ws_dict['name']} (GID: {ws_dict['gid']}){marker}")

            workspace_idx = click.prompt(
                "\nSelect workspace number",
                type=int,
                default=default_workspace_idx
            )
            workspace = workspaces_list[workspace_idx - 1]
            workspace_dict = workspace if isinstance(workspace, dict) else workspace.to_dict()
            config_data["ASANA_WORKSPACE_GID"] = workspace_dict["gid"]
            config_names["ASANA_WORKSPACE_GID"] = workspace_dict["name"]
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
                config_names["ASANA_TEAM_GID"] = team_dict["name"]
            else:
                console.print("\nFound teams:\n")

                default_team_idx = 1
                current_gid = existing_config.get("ASANA_TEAM_GID")

                for i, team in enumerate(teams_list, 1):
                    team_dict = team if isinstance(team, dict) else team.to_dict()
                    marker = ""
                    if current_gid and team_dict["gid"] == current_gid:
                        marker = " [bold green](Current)[/bold green]"
                        default_team_idx = i
                    console.print(f"  {i}. {team_dict['name']} (GID: {team_dict['gid']}){marker}")

                team_idx = click.prompt(
                    "\nSelect team number",
                    type=int,
                    default=default_team_idx
                )
                team = teams_list[team_idx - 1]
                team_dict = team if isinstance(team, dict) else team.to_dict()
                config_data["ASANA_TEAM_GID"] = team_dict["gid"]
                config_names["ASANA_TEAM_GID"] = team_dict["name"]

            console.print()
        else:
            # Not an organization, use workspace GID as team GID
            config_data["ASANA_TEAM_GID"] = workspace_gid
            config_names["ASANA_TEAM_GID"] = config_names.get("ASANA_WORKSPACE_GID", "Workspace")

        # Get Portfolio GID
        console.print("Now we need a Portfolio GID.")
        console.print("[dim]Portfolios group related projects. Aegis will monitor all projects in this portfolio.[/dim]\n")

        portfolios_api = asana.PortfoliosApi(api_client)
        users_api = asana.UsersApi(api_client)

        async def get_portfolios():
            # Need current user for owner param
            me = await asyncio.to_thread(
                users_api.get_user,
                "me",
                {"opt_fields": "gid"}
            )

            return await asyncio.to_thread(
                portfolios_api.get_portfolios,
                workspace_gid,
                {
                    "opt_fields": "name,gid",
                    "owner": me["gid"]
                }
            )

        portfolios = asyncio.run(get_portfolios())
        portfolios_list = list(portfolios)

        if len(portfolios_list) == 0:
            console.print("[yellow]No portfolios found in workspace[/yellow]")
            console.print("\nYou can:")
            console.print("  1. Create a portfolio in Asana")
            console.print("  2. Enter the portfolio GID manually later\n")

            portfolio_gid = click.prompt(
                "Enter portfolio GID (or press Enter to set later)",
                type=str,
                default=existing_config.get("ASANA_PORTFOLIO_GID", "")
            )
            if portfolio_gid:
                config_data["ASANA_PORTFOLIO_GID"] = portfolio_gid.strip()
                config_names["ASANA_PORTFOLIO_GID"] = "Manual Input"
            else:
                config_data["ASANA_PORTFOLIO_GID"] = "CHANGE_ME"
                config_names["ASANA_PORTFOLIO_GID"] = "Placeholder"

        elif len(portfolios_list) == 1:
            portfolio = portfolios_list[0]
            portfolio_dict = portfolio if isinstance(portfolio, dict) else portfolio.to_dict()
            console.print(f"[green]✓[/green] Found portfolio: {portfolio_dict['name']}")
            config_data["ASANA_PORTFOLIO_GID"] = portfolio_dict["gid"]
            config_names["ASANA_PORTFOLIO_GID"] = portfolio_dict["name"]
        else:
            console.print("Found portfolios:\n")

            default_portfolio_idx = 1
            current_gid = existing_config.get("ASANA_PORTFOLIO_GID")

            for i, portfolio in enumerate(portfolios_list, 1):
                portfolio_dict = portfolio if isinstance(portfolio, dict) else portfolio.to_dict()
                marker = ""
                if current_gid and portfolio_dict["gid"] == current_gid:
                    marker = " [bold green](Current)[/bold green]"
                    default_portfolio_idx = i
                console.print(f"  {i}. {portfolio_dict['name']} (GID: {portfolio_dict['gid']}){marker}")

            portfolio_idx = click.prompt(
                "\nSelect portfolio number",
                type=int,
                default=default_portfolio_idx
            )
            portfolio = portfolios_list[portfolio_idx - 1]
            portfolio_dict = portfolio if isinstance(portfolio, dict) else portfolio.to_dict()
            config_data["ASANA_PORTFOLIO_GID"] = portfolio_dict["gid"]
            config_names["ASANA_PORTFOLIO_GID"] = portfolio_dict["name"]

    except Exception as e:
        console.print(f"[red]Error testing Asana connection: {e}[/red]")
        console.print("[yellow]You can still continue and fix the credentials later[/yellow]\n")

        # Fallback to manual input
        workspace_gid = click.prompt(
            "Asana Workspace GID",
            type=str,
            default=existing_config.get("ASANA_WORKSPACE_GID", "")
        )
        config_data["ASANA_WORKSPACE_GID"] = workspace_gid.strip() or "CHANGE_ME"

        team_gid = click.prompt(
            "Asana Team GID",
            type=str,
            default=existing_config.get("ASANA_TEAM_GID", "")
        )
        config_data["ASANA_TEAM_GID"] = team_gid.strip() or config_data["ASANA_WORKSPACE_GID"]

        portfolio_gid = click.prompt(
            "Asana Portfolio GID",
            type=str,
            default=existing_config.get("ASANA_PORTFOLIO_GID", "")
        )
        config_data["ASANA_PORTFOLIO_GID"] = portfolio_gid.strip() or "CHANGE_ME"

    console.print()

    # -------------------------------------------------------------------------
    # Anthropic Configuration
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 2: Anthropic API Configuration[/bold cyan]\n")

    console.print("You'll need an Anthropic API key for Claude.")
    console.print("[dim]This allows Aegis agents to use Claude for task execution.[/dim]\n")

    default_key = existing_config.get("ANTHROPIC_API_KEY")

    if not default_key:
        if click.confirm("Open Anthropic API Keys page in browser?", default=True):
            webbrowser.open("https://console.anthropic.com/settings/keys")
            console.print("[green]✓[/green] Opened in browser\n")

        console.print("Steps to get your API key:")
        console.print("  1. Go to https://console.anthropic.com/settings/keys")
        console.print("  2. Click 'Create Key'")
        console.print("  3. Name it 'Aegis' and click 'Create Key'")
        console.print("  4. Copy the key (it starts with 'sk-ant-')\n")
    else:
        # Create masked default for display
        masked_default = f"...{default_key[-4:]}" if len(default_key) > 4 else default_key

    anthropic_key = click.prompt(
        "Paste your Anthropic API Key",
        type=str,
        default=default_key,
        show_default=masked_default if default_key else False,
    )
    config_data["ANTHROPIC_API_KEY"] = anthropic_key.strip()

    console.print()

    # -------------------------------------------------------------------------
    # Optional Configuration
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 3: Optional Configuration[/bold cyan]\n")

    default_db_url = existing_config.get("DATABASE_URL", "postgresql://localhost/aegis")

    if click.confirm("Configure database URL? (optional, press N to use default)", default=False):
        database_url = click.prompt(
            "Database URL",
            type=str,
            default=default_db_url
        )
        config_data["DATABASE_URL"] = database_url
    else:
        config_data["DATABASE_URL"] = default_db_url

    console.print()

    # -------------------------------------------------------------------------
    # Write .env file
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 4: Review and Save[/bold cyan]\n")

    # Prepare new content
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

    # Show diff if existing config
    if existing_config:
        console.print("[bold]Changes to .env:[/bold]")
        has_changes = False

        # Compare keys in new config
        for key, value in config_data.items():
            old_value = existing_config.get(key)
            if old_value != value:
                has_changes = True

                # Format value for display (add name if known)
                display_value = value
                if key in config_names:
                    display_value = f"{value} ({config_names[key]})"

                if "KEY" in key or "TOKEN" in key:
                    # Mask secrets
                    def mask(val):
                        if not val:
                            return "None"
                        if len(val) <= 8:
                            return "********"
                        return f"{val[:4]}...{val[-4:]}"

                    old_masked = mask(old_value)
                    new_masked = mask(value)
                    console.print(f"  [yellow]~ {key}: {old_masked} -> {new_masked}[/yellow]")
                else:
                    console.print(f"  [yellow]~ {key}: {old_value} -> {display_value}[/yellow]")

        if not has_changes:
            console.print("  [dim]No changes detected[/dim]")

        console.print()

        if not click.confirm("Apply these changes?", default=True):
            console.print("[dim]Configuration cancelled - no changes made[/dim]")
            return

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
        settings = Settings()

        console.print("[green]✓[/green] Configuration loaded successfully")
        console.print(f"  Workspace: {settings.asana_workspace_gid}")
        console.print(f"  Portfolio: {settings.asana_portfolio_gid}")
        console.print(f"  Model: {settings.anthropic_model}\n")

    except Exception as e:
        console.print(f"[yellow]Warning: Could not load configuration: {e}[/yellow]")
        console.print("[dim]You may need to edit .env manually[/dim]\n")

    # -------------------------------------------------------------------------
    # Step 6: Setup Custom Fields
    # -------------------------------------------------------------------------
    console.print("[bold cyan]Step 6: Setting up Asana Custom Fields[/bold cyan]\n")

    console.print("[dim]Running custom fields setup script...[/dim]\n")

    try:
        # Prepare environment
        env = os.environ.copy()
        env.update(config_data)

        # Run setup script
        setup_cmd = ["python", "tools/setup_asana_custom_fields.py"]
        subprocess.run(setup_cmd, check=True, env=env)
        console.print(f"\n[green]✓[/green] Custom fields setup complete\n")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]✗[/red] Custom fields setup failed: {e}")
        console.print("[yellow]You can run it manually later: python tools/setup_asana_custom_fields.py[/yellow]\n")

    # -------------------------------------------------------------------------
    # Next Steps
    # -------------------------------------------------------------------------
    console.print("[bold green]✓ Configuration Complete![/bold green]\n")

    console.print("[bold]Next Steps:[/bold]")
    console.print("  1. Sync project sections:")
    console.print("     [cyan]aegis sync[/cyan]\n")
    console.print("  2. Start the swarm:")
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


async def _parse_project_input(project: str, settings: Settings) -> str:
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

    return await _lookup()


def _resolve_task_gid(task_input: str, settings: Settings) -> str:
    """Resolve task GID from input.

    Args:
        task_input: Task GID or URL
        settings: Settings instance

    Returns:
        Task GID
    """
    import re

    # If it's a URL, extract GID
    if "asana.com" in task_input:
        # URL format: https://app.asana.com/0/project_gid/task_gid
        # or https://app.asana.com/0/0/task_gid
        parts = task_input.rstrip("/").split("/")
        candidate = parts[-1]
        if re.match(r"^\d{13,}$", candidate):
            return candidate
        raise ValueError(f"Could not extract task GID from URL: {task_input}")

    # If it's a GID (long number), return it
    if re.match(r"^\d{13,}$", task_input):
        return task_input

    raise ValueError(f"Invalid task ID or URL: {task_input}")


if __name__ == "__main__":
    main()
