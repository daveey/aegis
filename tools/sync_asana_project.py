#!/usr/bin/env python3
"""Sync Asana project sections and custom fields to match canonical structure.

This script enforces the canonical configuration defined in schema/asana_config.json.
It creates missing sections, reorders them, and ensures required custom fields are added.
"""

import asyncio
import json
import sys
from pathlib import Path

import structlog

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, Prompt
from aegis.asana.client import AsanaClient
from aegis.config import Settings

logger = structlog.get_logger()
console = Console()


async def load_schema() -> dict:
    """Load full schema from file.

    Returns:
        Dict containing canonical_sections and custom_fields
    """
    schema_file = Path(__file__).parent.parent / "schema" / "asana_config.json"

    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    with open(schema_file) as f:
        schema = json.load(f)

    return schema


async def get_workspace_custom_fields(client: AsanaClient, workspace_gid: str) -> dict[str, str]:
    """Get mapping of custom field names to GIDs in the workspace.

    Args:
        client: AsanaClient instance
        workspace_gid: Workspace GID

    Returns:
        Dict mapping field name to GID
    """
    # We need to use the lower-level API to list workspace custom fields
    # AsanaClient doesn't have a direct method for this yet, so we'll use the underlying api_client
    # Or better, let's use a helper if we can, but for now we'll implement it here using the client's api instance

    # Actually, setup_asana_custom_fields.py does this.
    # Let's use a similar approach but we need to be careful about not duplicating too much code.
    # However, since this is a standalone tool, it's okay to have some logic here.

    # We can use client.custom_fields_api
    custom_fields_api = client.custom_fields_api

    fields_generator = await asyncio.to_thread(
        custom_fields_api.get_custom_fields_for_workspace,
        workspace_gid,
        {"opt_fields": "name,gid"},
    )

    fields = {}
    for field in fields_generator:
        field_dict = field if isinstance(field, dict) else field.to_dict()
        fields[field_dict["name"]] = field_dict["gid"]

    return fields


async def sync_project_custom_fields(
    client: AsanaClient,
    project_gid: str,
    required_fields: list[dict],
    workspace_fields: dict[str, str],
    dry_run: bool = False,
) -> None:
    """Ensure project has all required custom fields.

    Args:
        client: AsanaClient instance
        project_gid: Project GID
        required_fields: List of custom field definitions from schema
        workspace_fields: Dict mapping field name to GID in workspace
        dry_run: If True, only log changes
    """
    logger.info("syncing_custom_fields", project_gid=project_gid)

    # Get project's current custom fields
    # We need to fetch project with custom_field_settings
    # AsanaClient.get_project doesn't fetch settings by default.
    # We can use the lower level API or just fetch the project again with specific opt_fields if needed,
    # but get_project fetches 'custom_fields' which are the values on tasks? No, on project it returns settings?
    # Actually get_project returns 'custom_fields' which are the field definitions/values on the project itself if it's a portfolio?
    # For a project, we want 'custom_field_settings'.

    # Let's use the custom_field_settings_api directly to get settings
    settings_response = await asyncio.to_thread(
        client.custom_field_settings_api.get_custom_field_settings_for_project,
        project_gid,
        {"opt_fields": "custom_field.name,custom_field.gid"},
    )

    current_field_gids = set()
    for setting in settings_response:
        setting_dict = setting if isinstance(setting, dict) else setting.to_dict()
        if setting_dict.get("custom_field"):
            current_field_gids.add(setting_dict["custom_field"]["gid"])

    # Check each required field
    for field_def in required_fields:
        field_name = field_def["name"]

        if field_name not in workspace_fields:
            logger.warning("custom_field_not_found_in_workspace", field_name=field_name)
            continue

        field_gid = workspace_fields[field_name]

        if field_gid not in current_field_gids:
            if not dry_run:
                try:
                    await client.add_custom_field_to_project(project_gid, field_gid)
                    logger.info("added_custom_field", project_gid=project_gid, field_name=field_name)
                except Exception as e:
                    logger.error("failed_to_add_custom_field", field_name=field_name, error=str(e))
            else:
                logger.info("would_add_custom_field", field_name=field_name)
        else:
            logger.debug("custom_field_already_present", field_name=field_name)


async def sync_project(
    client: AsanaClient,
    project_gid: str,
    schema: dict,
    workspace_fields: dict[str, str],
    dry_run: bool = False,
) -> None:
    """Sync sections and custom fields for a single project.

    Args:
        client: AsanaClient instance
        project_gid: Project GID
        schema: Full schema dict
        workspace_fields: Dict mapping field name to GID
        dry_run: If True, only log changes
    """
    logger.info("syncing_project", project_gid=project_gid, dry_run=dry_run)

    # 1. Sync Sections
    canonical_sections = schema["canonical_sections"]
    current_sections = await client.get_sections(project_gid)
    current_section_names = [s.name for s in current_sections]

    canonical_names = [s["name"] for s in canonical_sections]
    missing_sections = [name for name in canonical_names if name not in current_section_names]

    if missing_sections:
        logger.info("creating_missing_sections", sections=missing_sections)
        for section_name in missing_sections:
            if not dry_run:
                try:
                    await client.create_section(project_gid, section_name)
                    logger.info("section_created", section_name=section_name)
                except Exception as e:
                    logger.error("section_creation_failed", section_name=section_name, error=str(e))
            else:
                logger.info("would_create_section", section_name=section_name)

    # 1.5 Reorder Sections
    # Refresh sections to get new GIDs and current order
    current_sections = await client.get_sections(project_gid)
    section_map = {s.name: s for s in current_sections}
    current_gids = [s.gid for s in current_sections]

    previous_gid = None

    for section_def in canonical_sections:
        section_name = section_def["name"]
        if section_name not in section_map:
            continue

        section_gid = section_map[section_name].gid

        # Check if already in correct position relative to previous
        # If previous_gid is None, this should be the first section (index 0)
        # If previous_gid is set, this should be immediately after it?
        # Actually, as long as it is *after* it, it's okay? No, we want exact order.

        should_move = False

        if previous_gid is None:
            # Should be first
            if current_gids[0] != section_gid:
                should_move = True
        else:
            # Should be after previous_gid
            try:
                prev_index = current_gids.index(previous_gid)
                curr_index = current_gids.index(section_gid)
                if curr_index != prev_index + 1:
                    should_move = True
            except ValueError:
                should_move = True

        if should_move:
            if not dry_run:
                try:
                    await client.reorder_section(
                        project_gid,
                        section_gid,
                        after_section_gid=previous_gid
                    )
                    logger.info("reordered_section", section_name=section_name, after=previous_gid)

                    # Update local list to reflect change for next iteration
                    current_gids.remove(section_gid)
                    if previous_gid is None:
                        current_gids.insert(0, section_gid)
                    else:
                        prev_index = current_gids.index(previous_gid)
                        current_gids.insert(prev_index + 1, section_gid)

                except Exception as e:
                    logger.error("reorder_failed", section_name=section_name, error=str(e))
            else:
                logger.info("would_reorder_section", section_name=section_name, after=previous_gid)

        previous_gid = section_gid

    # 2. Sync Custom Fields
    await sync_project_custom_fields(
        client,
        project_gid,
        schema["custom_fields"],
        workspace_fields,
        dry_run=dry_run
    )

    logger.info("project_sync_complete", project_gid=project_gid)


async def sync_portfolio_projects(
    client: AsanaClient,
    portfolio_gid: str,
    schema: dict,
    workspace_fields: dict[str, str],
    dry_run: bool = False,
) -> list[dict]:
    """Sync all projects in a portfolio.

    Args:
        client: AsanaClient instance
        portfolio_gid: Portfolio GID
        schema: Full schema
        workspace_fields: Workspace custom fields map
        dry_run: If True, only log changes

    Returns:
        List of synced projects
    """
    logger.info("syncing_portfolio", portfolio_gid=portfolio_gid)

    projects = await client.get_portfolio_projects(portfolio_gid)

    if not projects:
        return []

    # Interactive selection
    projects_to_sync = []

    if dry_run:
        projects_to_sync = projects
    else:
        console.print(f"\n[bold]Found {len(projects)} projects in portfolio:[/bold]")
        for i, p in enumerate(projects, 1):
            console.print(f"  {i}. {p.name} ({p.gid})")

        if Confirm.ask("\nSync all projects?", default=True):
            projects_to_sync = projects
        else:
            selection = Prompt.ask("Enter project numbers to sync (comma separated)", default="all")
            if selection.lower() == "all":
                projects_to_sync = projects
            else:
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(",")]
                    projects_to_sync = [projects[i] for i in indices if 0 <= i < len(projects)]
                except (ValueError, IndexError):
                    console.print("[red]Invalid selection, syncing none.[/red]")
                    return []

    synced_projects = []

    for project in projects_to_sync:
        try:
            await sync_project(
                client,
                project.gid,
                schema,
                workspace_fields,
                dry_run=dry_run,
            )
            synced_projects.append({"name": project.name, "gid": project.gid})
        except Exception as e:
            logger.error("project_sync_failed", project_gid=project.gid, error=str(e))

    return synced_projects


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync Asana project sections and custom fields")
    parser.add_argument(
        "--project",
        action="append",
        help="Project GID to sync (can be specified multiple times)",
    )
    parser.add_argument(
        "--portfolio",
        help="Portfolio GID to sync all projects (uses env var if not specified)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be changed, don't apply",
    )

    args = parser.parse_args()

    settings = Settings()
    schema = await load_schema()
    client = AsanaClient(settings.asana_access_token)

    # Fetch workspace fields once
    console.print("[dim]Fetching workspace custom fields...[/dim]")
    workspace_fields = await get_workspace_custom_fields(client, settings.asana_workspace_gid)
    console.print(f"[dim]Found {len(workspace_fields)} custom fields in workspace[/dim]")

    if args.project:
        projects_to_sync = args.project
        console.print(f"[bold]Syncing {len(projects_to_sync)} specified project(s)...[/bold]")

        synced_count = 0
        for project_gid in projects_to_sync:
            try:
                await sync_project(
                    client,
                    project_gid,
                    schema,
                    workspace_fields,
                    dry_run=args.dry_run,
                )
                console.print(f"[green]✓[/green] Synced project {project_gid}")
                synced_count += 1
            except Exception as e:
                console.print(f"[red]✗ Failed to sync project {project_gid}: {e}[/red]")

        if synced_count > 0:
             console.print(f"\n[green]✓ Successfully synced {synced_count} project(s)[/green]")

    elif args.portfolio or settings.asana_portfolio_gid:
        portfolio_gid = args.portfolio or settings.asana_portfolio_gid
        synced_projects = await sync_portfolio_projects(
            client,
            portfolio_gid,
            schema,
            workspace_fields,
            dry_run=args.dry_run,
        )

        if synced_projects:
            console.print(f"\n[bold green]✓ Synced {len(synced_projects)} projects:[/bold green]")
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("Project Name")
            table.add_column("GID", style="dim")
            for project in synced_projects:
                table.add_row(project["name"], project["gid"])
            console.print(table)
        else:
            console.print("\n[yellow]No projects found or synced.[/yellow]")

    else:
        logger.error("no_target_specified", message="Specify --project or --portfolio")
        sys.exit(1)

    logger.info("sync_complete")


if __name__ == "__main__":
    asyncio.run(main())
