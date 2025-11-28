#!/usr/bin/env python3
"""Add all active workspace projects to the Aegis portfolio."""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import asana

from aegis.config import get_settings


async def add_projects_to_portfolio(portfolio_gid: str) -> None:
    """Add all active workspace projects to the specified portfolio."""
    settings = get_settings()

    # Configure API client
    configuration = asana.Configuration()
    configuration.access_token = settings.asana_access_token
    api_client = asana.ApiClient(configuration)

    projects_api = asana.ProjectsApi(api_client)
    portfolios_api = asana.PortfoliosApi(api_client)

    try:
        workspace_gid = settings.asana_workspace_gid
        print(f"Fetching all projects in workspace {workspace_gid}...")

        # Get all active projects in workspace
        projects_list = await asyncio.to_thread(
            projects_api.get_projects,
            {
                "workspace": workspace_gid,
                "opt_fields": "name,gid,archived"
            }
        )

        active_projects = [p for p in projects_list if not p.get('archived')]

        print(f"Found {len(active_projects)} active projects")
        print(f"\nAdding projects to portfolio {portfolio_gid}...")

        added_count = 0
        failed_count = 0

        for project in active_projects:
            try:
                # Add project to portfolio
                await asyncio.to_thread(
                    portfolios_api.add_item_for_portfolio,
                    {"data": {"project": project['gid']}},
                    portfolio_gid
                )
                print(f"  ✓ Added: {project['name']}")
                added_count += 1
            except Exception as e:
                # Project might already be in portfolio or other error
                print(f"  ✗ Failed: {project['name']} - {str(e)[:50]}")
                failed_count += 1

        print(f"\n{'='*60}")
        print("Summary:")
        print(f"  Added: {added_count}")
        print(f"  Failed: {failed_count}")
        print(f"  Total: {len(active_projects)}")
        print(f"{'='*60}")

        # Generate .env update
        project_gids = ",".join([p['gid'] for p in active_projects])
        print("\nUpdate .env with:")
        print(f"ASANA_PROJECT_GIDS={project_gids}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Portfolio GID from the URL: https://app.asana.com/0/portfolio/1212078048284635/1212085171241424
    portfolio_gid = "1212078048284635"

    print(f"{'='*60}")
    print("Adding all active projects to Aegis portfolio")
    print(f"{'='*60}\n")

    asyncio.run(add_projects_to_portfolio(portfolio_gid))
