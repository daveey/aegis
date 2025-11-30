import asyncio
import os
from pathlib import Path
from aegis.config import Settings
from aegis.asana.client import AsanaClient
from aegis.core.tracker import ProjectTracker

async def track_aegis():
    settings = Settings()
    client = AsanaClient(settings.asana_access_token)
    tracker = ProjectTracker()

    print("Fetching projects from workspace...")
    # Use underlying API directly since wrapper is missing get_projects
    projects = client.projects_api.get_projects(
        {
            'workspace': settings.asana_workspace_gid,
            'archived': False,
            'opt_fields': "name,gid"
        }
    )

    aegis_project = None
    for p in projects:
        print(f"Found project in workspace: {p['name']} ({p['gid']})")
        if "aegis" in p['name'].lower():
            aegis_project = p
            break

    if not aegis_project:
        print("Could not find project 'Aegis' in workspace.")
        return

    print(f"Found project: {aegis_project['name']} ({aegis_project['gid']})")

    cwd = Path.cwd()
    print(f"Tracking at: {cwd}")

    tracker.add_project(aegis_project['gid'], aegis_project['name'], cwd)
    print("Successfully added to tracking.")

if __name__ == "__main__":
    asyncio.run(track_aegis())
