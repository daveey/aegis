"""Example usage of the SimpleExecutor agent.

This script demonstrates how to use the SimpleExecutor agent to process
an Asana task using the Claude API.

Usage:
    python examples/simple_executor_usage.py <task_gid>

Example:
    python examples/simple_executor_usage.py 1234567890
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aegis.agents.simple_executor import SimpleExecutor
from aegis.asana.client import AsanaClient
from aegis.config import Settings


async def main():
    """Main execution function."""
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python simple_executor_usage.py <task_gid>")
        print("\nExample: python simple_executor_usage.py 1234567890")
        sys.exit(1)

    task_gid = sys.argv[1]

    # Load configuration
    print("Loading configuration...")
    config = Settings()

    # Initialize clients
    print("Initializing Asana client...")
    asana_client = AsanaClient(config.asana_access_token)

    print("Initializing SimpleExecutor agent...")
    executor = SimpleExecutor(config=config, asana_client=asana_client)

    # Fetch the task
    print(f"\nFetching task {task_gid}...")
    task = await asana_client.get_task(task_gid)
    print(f"Task: {task.name}")
    if task.notes:
        print(f"Description: {task.notes[:200]}...")

    # Get project information
    project_name = "Unknown"
    code_path = None
    if task.projects:
        project = task.projects[0]
        project_name = project.name
        # Try to get code path from project notes
        project_details = await asana_client.get_project(project.gid)
        if project_details.notes:
            for line in project_details.notes.split("\n"):
                if line.startswith("Code Location:"):
                    code_path = line.split(":", 1)[1].strip()
                    break

    print(f"Project: {project_name}")
    if code_path:
        print(f"Code Location: {code_path}")

    # Execute the task
    print("\n" + "=" * 60)
    print("Executing task with SimpleExecutor agent...")
    print("=" * 60 + "\n")

    result = await executor.execute_task(
        task=task,
        project_name=project_name,
        code_path=code_path,
    )

    # Display results
    print("\n" + "=" * 60)
    print("Execution Results")
    print("=" * 60)
    print(f"Success: {result['success']}")
    print(f"Execution ID: {result['execution_id']}")

    if result["success"]:
        print(f"\nResponse posted to Asana task {task_gid}")
        if result["metadata"]:
            print(f"Input tokens: {result['metadata'].get('input_tokens', 'N/A')}")
            print(f"Output tokens: {result['metadata'].get('output_tokens', 'N/A')}")
            print(f"Model: {result['metadata'].get('model', 'N/A')}")
    else:
        print(f"\nError: {result['error']}")
        print("Error details posted to Asana task")

    print("\n✅ Done!")


if __name__ == "__main__":
    asyncio.run(main())
