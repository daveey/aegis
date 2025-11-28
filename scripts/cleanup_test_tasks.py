#!/usr/bin/env python3
"""Cleanup script for E2E test tasks in Asana.

This script removes test tasks created during integration testing.
It safely deletes only tasks that match the E2E test pattern.

Usage:
    python scripts/cleanup_test_tasks.py [--dry-run] [--project-gid GID]

Environment Variables:
    ASANA_ACCESS_TOKEN: Asana Personal Access Token
    ASANA_TEST_PROJECT_GID: Test project GID (or use --project-gid)
"""

import argparse
import asyncio
import os
import sys

import asana
from rich.console import Console
from rich.table import Table

console = Console()


async def cleanup_test_tasks(project_gid: str, dry_run: bool = False) -> None:
    """Clean up test tasks from an Asana project.

    Args:
        project_gid: GID of the project to clean
        dry_run: If True, only show what would be deleted without actually deleting
    """
    try:
        access_token = os.getenv("ASANA_ACCESS_TOKEN")
        if not access_token:
            console.print("[red]Error: ASANA_ACCESS_TOKEN not set[/red]")
            sys.exit(1)

        # Configure API client
        configuration = asana.Configuration()
        configuration.access_token = access_token
        api_client = asana.ApiClient(configuration)
        tasks_api = asana.TasksApi(api_client)
        projects_api = asana.ProjectsApi(api_client)

        # Get project details
        console.print(f"[bold]Fetching project details for GID: {project_gid}[/bold]")
        project = await asyncio.to_thread(
            projects_api.get_project,
            project_gid,
            {"opt_fields": "name,gid"}
        )
        console.print(f"Project: {project['name']}\n")

        # Get all tasks
        console.print("Fetching tasks...")
        tasks_generator = await asyncio.to_thread(
            tasks_api.get_tasks_for_project,
            project_gid,
            {"opt_fields": "name,gid,completed,created_at,permalink_url"}
        )
        all_tasks = list(tasks_generator)

        # Filter test tasks
        test_tasks = [
            task for task in all_tasks
            if task["name"].startswith("E2E_TEST_")
        ]

        if not test_tasks:
            console.print("[green]No test tasks found. Nothing to clean up![/green]")
            return

        # Display tasks to be deleted
        table = Table(title=f"Test Tasks to {'Review' if dry_run else 'Delete'}")
        table.add_column("Name", style="cyan")
        table.add_column("GID", style="magenta")
        table.add_column("Completed", style="yellow")
        table.add_column("Created", style="blue")

        for task in test_tasks:
            completed_status = "✓" if task.get("completed") else "✗"
            created_at = task.get("created_at", "Unknown")
            if isinstance(created_at, str) and "T" in created_at:
                created_at = created_at.split("T")[0]

            table.add_row(
                task["name"],
                task["gid"],
                completed_status,
                str(created_at)
            )

        console.print(table)
        console.print(f"\n[bold]Total test tasks found: {len(test_tasks)}[/bold]\n")

        if dry_run:
            console.print("[yellow]DRY RUN MODE - No tasks will be deleted[/yellow]")
            console.print("Run without --dry-run to actually delete these tasks")
            return

        # Confirm deletion
        console.print("[bold red]WARNING: This will permanently delete these tasks![/bold red]")
        response = input("Are you sure you want to continue? (yes/no): ")

        if response.lower() != "yes":
            console.print("[yellow]Cancelled by user[/yellow]")
            return

        # Delete tasks
        console.print("\n[bold]Deleting tasks...[/bold]")
        deleted_count = 0
        failed_count = 0

        for task in test_tasks:
            try:
                # Mark as completed first (softer delete)
                await asyncio.to_thread(
                    tasks_api.update_task,
                    {"data": {"completed": True}},
                    task["gid"],
                    {}
                )

                # Then delete
                await asyncio.to_thread(
                    tasks_api.delete_task,
                    task["gid"]
                )

                console.print(f"  [green]✓[/green] Deleted: {task['name']}")
                deleted_count += 1

            except Exception as e:
                console.print(f"  [red]✗[/red] Failed to delete {task['name']}: {e}")
                failed_count += 1

        # Summary
        console.print("\n[bold]Cleanup Summary[/bold]")
        console.print(f"  [green]Deleted: {deleted_count}[/green]")
        if failed_count > 0:
            console.print(f"  [red]Failed: {failed_count}[/red]")
        console.print("\n[green]✓ Cleanup complete![/green]")

    except Exception as e:
        console.print(f"[red]Error during cleanup: {e}[/red]")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Clean up E2E test tasks from Asana project"
    )
    parser.add_argument(
        "--project-gid",
        help="Asana project GID (or set ASANA_TEST_PROJECT_GID env var)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting",
    )

    args = parser.parse_args()

    # Get project GID
    project_gid = args.project_gid or os.getenv("ASANA_TEST_PROJECT_GID")

    if not project_gid:
        console.print(
            "[red]Error: Project GID required. "
            "Use --project-gid or set ASANA_TEST_PROJECT_GID[/red]"
        )
        sys.exit(1)

    # Run cleanup
    asyncio.run(cleanup_test_tasks(project_gid, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
