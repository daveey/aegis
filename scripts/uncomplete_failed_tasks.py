#!/usr/bin/env python3
"""
Script to identify and uncomplete failed tasks in Aegis project.
"""
import asyncio

import structlog

from aegis.asana.client import AsanaClient
from aegis.asana.models import AsanaTaskUpdate
from aegis.config import Settings

logger = structlog.get_logger()


async def main():
    """Find failed tasks and move them back to Ready to Implement."""
    config = Settings()
    client = AsanaClient(config.asana_access_token)

    # Get Aegis project GID
    aegis_project_gid = "1212085431574340"

    print("Fetching tasks from Aegis project...")

    # Get all tasks from the project
    tasks = await client.get_tasks_from_project(aegis_project_gid, assigned_only=False)

    # Filter for completed tasks
    completed_tasks = [t for t in tasks if t.completed]
    print(f"Found {len(completed_tasks)} completed tasks")

    # Get sections
    sections = await client.get_sections(aegis_project_gid)
    sections_by_name = {s.name: s.gid for s in sections}

    print("\nAvailable sections:")
    for name in sections_by_name:
        print(f"  - {name}")

    ready_section_gid = sections_by_name.get("Ready to Implement")
    if not ready_section_gid:
        print("ERROR: 'Ready to Implement' section not found!")
        return

    # Check each completed task for failures
    failed_tasks = []

    print(f"\nChecking {len(completed_tasks)} completed tasks for failures...")

    for task in completed_tasks:
        # Check comments for failure indicators
        comments = await client.get_comments(task.gid)

        has_failure = False
        failure_comment = None

        for comment in comments:
            text = comment.text.lower()
            # Look for clear failure indicators
            if any(keyword in text for keyword in [
                "❌ execution failed",
                "failed with error",
                "error:",
                "exception:",
                "traceback",
                "failed to execute"
            ]):
                has_failure = True
                failure_comment = comment.text
                break

        if has_failure:
            print(f"\n❌ FAILED: {task.name} (GID: {task.gid})")
            if failure_comment:
                print(f"   Comment preview: {failure_comment[:300]}...")
            failed_tasks.append((task, failure_comment))

    print(f"\n{'='*80}")
    print(f"Found {len(failed_tasks)} failed tasks")
    print(f"{'='*80}\n")

    if not failed_tasks:
        print("No failed tasks found!")
        return

    # Show tasks to be processed
    print("Tasks to uncomplete and move back to 'Ready to Implement':")
    for i, (task, _) in enumerate(failed_tasks, 1):
        print(f"{i}. {task.name}")

    print("\nProceeding with uncompleting these tasks...")

    # Uncomplete and move tasks
    print("\nProcessing tasks...")
    for task, failure_comment in failed_tasks:
        try:
            # Uncomplete the task
            await client.update_task(
                task.gid,
                AsanaTaskUpdate(completed=False)
            )
            print(f"✓ Uncompleted: {task.name}")

            # Move to Ready to Implement section
            await client.move_task_to_section(
                task.gid,
                aegis_project_gid,
                ready_section_gid
            )
            print(f"✓ Moved to 'Ready to Implement': {task.name}")

            # Add a comment explaining what happened
            comment_text = (
                "🔄 This task was marked as complete but the execution failed. "
                "Moving back to 'Ready to Implement' for retry."
            )

            await client.add_comment(task.gid, comment_text)
            print("✓ Added explanatory comment\n")

        except Exception as e:
            print(f"❌ Error processing {task.name}: {e}\n")

    print(f"\n{'='*80}")
    print(f"Completed! Processed {len(failed_tasks)} tasks")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
