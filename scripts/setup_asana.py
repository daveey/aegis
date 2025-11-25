#!/usr/bin/env python3
"""Helper script to extract workspace and project information from Asana portfolio."""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aegis.config import get_settings
import asana


async def get_portfolio_info(portfolio_gid: str) -> None:
    """Get information about a portfolio including workspace and projects."""
    settings = get_settings()

    # Configure API client
    configuration = asana.Configuration()
    configuration.access_token = settings.asana_access_token
    api_client = asana.ApiClient(configuration)

    portfolios_api = asana.PortfoliosApi(api_client)

    try:
        print(f"Fetching portfolio {portfolio_gid}...")

        # Get portfolio details
        portfolio_dict = await asyncio.to_thread(
            portfolios_api.get_portfolio,
            portfolio_gid,
            {"opt_fields": "name,workspace.gid,workspace.name"}
        )

        print(f"\nPortfolio: {portfolio_dict['name']}")

        if portfolio_dict.get('workspace'):
            workspace_gid = portfolio_dict['workspace']['gid']
            workspace_name = portfolio_dict['workspace']['name']
            print(f"Workspace: {workspace_name} (GID: {workspace_gid})")
        else:
            print("Warning: No workspace information found")
            return

        # Get all projects in the portfolio
        print(f"\nFetching projects in portfolio...")
        projects_list = await asyncio.to_thread(
            portfolios_api.get_items_for_portfolio,
            portfolio_gid,
            {"opt_fields": "name,gid"}
        )

        projects = []
        for project_dict in projects_list:
            projects.append(project_dict)
            print(f"  - {project_dict['name']} (GID: {project_dict['gid']})")

        print(f"\nTotal projects: {len(projects)}")

        # Generate .env entries
        print("\n" + "="*60)
        print("Add these to your .env file:")
        print("="*60)
        print(f"ASANA_WORKSPACE_GID={workspace_gid}")
        project_gids = ",".join([p['gid'] for p in projects])
        print(f"ASANA_PROJECT_GIDS={project_gids}")
        print("="*60)

        return workspace_gid, [p['gid'] for p in projects]

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None, []


if __name__ == "__main__":
    # Portfolio GID from the URL: https://app.asana.com/0/portfolio/1212078048284635/1212085171241424
    portfolio_gid = "1212078048284635"

    result = asyncio.run(get_portfolio_info(portfolio_gid))

    if result:
        workspace_gid, project_gids = result
        print(f"\nWorkspace GID: {workspace_gid}")
        print(f"Project GIDs: {', '.join(project_gids)}")
