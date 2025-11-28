"""Helper functions for agents to complete tasks and post comments.

This module provides simple functions that agents can call directly
to interact with Asana after completing their work.
"""

import asyncio

from aegis.asana.client import AsanaClient
from aegis.config import get_settings


async def post_comment_and_complete_task(
    task_gid: str,
    project_gid: str,
    comment_text: str
) -> None:
    """Post a comment to a task and mark it as complete.

    Args:
        task_gid: The GID of the task
        project_gid: The GID of the project
        comment_text: The comment text (summary of work done)
    """
    settings = get_settings()
    client = AsanaClient(settings.asana_access_token)

    # Post comment
    await client.add_comment(task_gid, comment_text)
    print(f"✓ Posted comment to task {task_gid}")

    # Complete task and move to Implemented section
    await client.complete_task_and_move_to_implemented(task_gid, project_gid)
    print(f"✓ Task {task_gid} marked complete and moved to Implemented")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 4:
        print("Usage: python -m aegis.agent_helpers TASK_GID PROJECT_GID COMMENT_TEXT")
        sys.exit(1)

    task_gid = sys.argv[1]
    project_gid = sys.argv[2]
    comment_text = sys.argv[3]

    asyncio.run(post_comment_and_complete_task(task_gid, project_gid, comment_text))
