#!/usr/bin/env python3
"""List all projects in the Softmax workspace."""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import asana

from aegis.config import get_settings


async def list_workspace_projects() -> None:
    """List all projects in the workspace."""
    settings = get_settings()

    # Configure API client
    configuration = asana.Configuration()
    configuration.access_token = settings.asana_access_token
    api_client = asana.ApiClient(configuration)

    projects_api = asana.ProjectsApi(api_client)

    try:
        workspace_gid = settings.asana_workspace_gid
        print(f"Fetching all projects in workspace {workspace_gid}...")

        # Get all projects in workspace
        projects_list = await asyncio.to_thread(
            projects_api.get_projects,
            {
                "workspace": workspace_gid,
                "opt_fields": "name,gid,archived,public"
            }
        )

        active_projects = []
        archived_projects = []

        for project_dict in projects_list:
            if project_dict.get('archived'):
                archived_projects.append(project_dict)
            else:
                active_projects.append(project_dict)

        print(f"\n{'='*60}")
        print(f"Active Projects ({len(active_projects)}):")
        print(f"{'='*60}")
        for project in active_projects:
            visibility = "Public" if project.get('public') else "Private"
            print(f"  - {project['name']}")
            print(f"    GID: {project['gid']}")
            print(f"    Visibility: {visibility}")
            print()

        if archived_projects:
            print(f"\n{'='*60}")
            print(f"Archived Projects ({len(archived_projects)}):")
            print(f"{'='*60}")
            for project in archived_projects:
                print(f"  - {project['name']} (GID: {project['gid']})")

        # Generate instructions
        print(f"\n{'='*60}")
        print("Next Steps:")
        print(f"{'='*60}")
        print("To add these projects to the Aegis portfolio:")
        print("1. Go to: https://app.asana.com/0/portfolio/1212078048284635")
        print("2. Click 'Add Project' button")
        print("3. Select the projects you want to monitor with Aegis")
        print("\nOr use the Asana API to add them programmatically.")
        print(f"{'='*60}")

        # Show what to add to .env after adding projects to portfolio
        if active_projects:
            project_gids = ",".join([p['gid'] for p in active_projects])
            print("\nAfter adding projects to portfolio, update .env:")
            print(f"ASANA_PROJECT_GIDS={project_gids}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(list_workspace_projects())
