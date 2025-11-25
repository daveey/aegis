#!/usr/bin/env python3
"""Add an existing project to the Aegis portfolio."""

import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aegis.config import get_settings
import asana


async def add_to_portfolio(project_gid: str) -> None:
    """Add a project to the Aegis portfolio.

    Args:
        project_gid: Project GID to add
    """
    settings = get_settings()

    # Configure API client
    configuration = asana.Configuration()
    configuration.access_token = settings.asana_access_token
    api_client = asana.ApiClient(configuration)

    portfolios_api = asana.PortfoliosApi(api_client)

    try:
        portfolio_gid = settings.asana_portfolio_gid

        print(f"Adding project {project_gid} to portfolio {portfolio_gid}...")

        await asyncio.to_thread(
            portfolios_api.add_item_for_portfolio,
            {"data": {"item": project_gid}},
            portfolio_gid
        )

        print(f"✓ Added to portfolio: https://app.asana.com/0/portfolio/{portfolio_gid}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Add project to Aegis portfolio")
    parser.add_argument("project_gid", help="Project GID to add")

    args = parser.parse_args()

    asyncio.run(add_to_portfolio(args.project_gid))
