#!/usr/bin/env python3
"""Create a new Asana project and add it to the Aegis portfolio."""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import asana

from aegis.config import get_settings


async def create_project(name: str, code_path: str | None = None) -> str:
    """Create a new Asana project and add it to the Aegis portfolio.

    Args:
        name: Project name
        code_path: Optional path to code directory

    Returns:
        Project GID
    """
    settings = get_settings()

    # Configure API client
    configuration = asana.Configuration()
    configuration.access_token = settings.asana_access_token
    api_client = asana.ApiClient(configuration)

    projects_api = asana.ProjectsApi(api_client)
    portfolios_api = asana.PortfoliosApi(api_client)
    teams_api = asana.TeamsApi(api_client)

    try:
        workspace_gid = settings.asana_workspace_gid
        portfolio_gid = settings.asana_portfolio_gid

        # Get teams in workspace
        print(f"Getting teams in workspace {workspace_gid}...")
        teams_generator = await asyncio.to_thread(
            teams_api.get_teams_for_workspace,
            workspace_gid,
            {}
        )
        teams_list = list(teams_generator)

        if not teams_list:
            print("Error: No teams found in workspace. Projects require a team.")
            sys.exit(1)

        # Use the first team
        team_gid = teams_list[0]['gid']
        team_name = teams_list[0].get('name', 'Unknown')
        print(f"Using team: {team_name} (GID: {team_gid})")

        print(f"\nCreating project '{name}'...")

        # Build project notes
        notes = "Code managed by Aegis\n"
        if code_path:
            # Expand home directory
            expanded_path = os.path.expanduser(code_path)
            notes += f"\nCode Location: {expanded_path}"

        # Create project
        project_data = {
            "data": {
                "name": name,
                "team": team_gid,
                "notes": notes,
                "public": False,
            }
        }

        project_dict = await asyncio.to_thread(
            projects_api.create_project,
            project_data,
            {"opt_fields": "name,gid,permalink_url"}
        )

        project_gid = project_dict['gid']
        project_url = project_dict.get('permalink_url', '')

        print(f"✓ Created project: {name}")
        print(f"  GID: {project_gid}")
        if project_url:
            print(f"  URL: {project_url}")

        # Try to add to Aegis portfolio
        print("\nAdding project to Aegis portfolio...")
        try:
            await asyncio.to_thread(
                portfolios_api.add_item_for_portfolio,
                {"data": {"item": project_gid}},
                portfolio_gid
            )
            print(f"✓ Added to portfolio: https://app.asana.com/0/portfolio/{portfolio_gid}")
        except Exception as e:
            print(f"⚠ Could not auto-add to portfolio: {e}")
            print(f"  Please add manually at: https://app.asana.com/0/portfolio/{portfolio_gid}")

        return project_gid

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create Asana project for code management")
    parser.add_argument("name", help="Project name")
    parser.add_argument("--code-path", help="Path to code directory", default=None)

    args = parser.parse_args()

    print(f"{'='*60}")
    print("Creating Asana Project")
    print(f"{'='*60}\n")

    project_gid = asyncio.run(create_project(args.name, args.code_path))

    print(f"\n{'='*60}")
    print("Project created successfully!")
    print(f"GID: {project_gid}")
    print(f"{'='*60}")
