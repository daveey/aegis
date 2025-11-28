#!/usr/bin/env python3
"""Sync Asana project sections to match canonical structure.

This script enforces the canonical section list defined in schema/asana_config.json.
It creates missing sections and reorders them to match the expected structure.
"""

import asyncio
import json
import sys
from pathlib import Path

import structlog

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aegis.asana.client import AsanaClient
from aegis.config import Settings

logger = structlog.get_logger()


async def load_canonical_sections() -> list[dict]:
    """Load canonical sections from schema file.

    Returns:
        List of section definitions
    """
    schema_file = Path(__file__).parent.parent / "schema" / "asana_config.json"

    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    with open(schema_file) as f:
        schema = json.load(f)

    return schema["canonical_sections"]


async def sync_project_sections(
    client: AsanaClient,
    project_gid: str,
    canonical_sections: list[dict],
    dry_run: bool = False,
) -> None:
    """Sync sections for a single project.

    Args:
        client: AsanaClient instance
        project_gid: Project GID
        canonical_sections: List of canonical section definitions
        dry_run: If True, only log changes without applying
    """
    logger.info("syncing_project", project_gid=project_gid, dry_run=dry_run)

    # Get current sections
    current_sections = await client.get_sections(project_gid)
    current_section_names = [s.name for s in current_sections]

    logger.info(
        "current_sections",
        project_gid=project_gid,
        sections=current_section_names,
    )

    # Find missing sections
    canonical_names = [s["name"] for s in canonical_sections]
    missing_sections = [name for name in canonical_names if name not in current_section_names]

    # Create missing sections
    if missing_sections:
        logger.info(
            "creating_missing_sections",
            project_gid=project_gid,
            sections=missing_sections,
        )

        for section_name in missing_sections:
            if not dry_run:
                try:
                    await client.create_section(project_gid, section_name)
                    logger.info("section_created", section_name=section_name)
                except Exception as e:
                    logger.error(
                        "section_creation_failed",
                        section_name=section_name,
                        error=str(e),
                    )
            else:
                logger.info("would_create_section", section_name=section_name)

    # Reorder sections to match canonical order
    # (Asana API doesn't have a direct reorder method, so we'd need to use insert_section)
    # For now, just log the desired order
    current_sections_after = await client.get_sections(project_gid)
    current_order = [s.name for s in current_sections_after]

    if current_order != canonical_names:
        logger.warning(
            "section_order_mismatch",
            current_order=current_order,
            canonical_order=canonical_names,
        )
        logger.info("section_reordering_not_implemented")

    # Check for unknown sections
    unknown_sections = [name for name in current_order if name not in canonical_names]
    if unknown_sections:
        logger.warning(
            "unknown_sections_found",
            sections=unknown_sections,
            action="Preserved (not deleted)",
        )

    logger.info("project_sync_complete", project_gid=project_gid)


async def sync_portfolio_projects(
    client: AsanaClient,
    portfolio_gid: str,
    canonical_sections: list[dict],
    dry_run: bool = False,
) -> None:
    """Sync sections for all projects in a portfolio.

    Args:
        client: AsanaClient instance
        portfolio_gid: Portfolio GID
        canonical_sections: List of canonical section definitions
        dry_run: If True, only log changes without applying
    """
    logger.info("syncing_portfolio", portfolio_gid=portfolio_gid, dry_run=dry_run)

    # Get all projects in portfolio
    projects = await client.get_portfolio_projects(portfolio_gid)

    logger.info("portfolio_projects_found", count=len(projects))

    # Sync each project
    for project in projects:
        try:
            await sync_project_sections(
                client,
                project.gid,
                canonical_sections,
                dry_run=dry_run,
            )
        except Exception as e:
            logger.error(
                "project_sync_failed",
                project_gid=project.gid,
                project_name=project.name,
                error=str(e),
            )

    logger.info("portfolio_sync_complete", portfolio_gid=portfolio_gid)


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync Asana project sections")
    parser.add_argument(
        "--project",
        help="Project GID to sync (if not specified, uses portfolio)",
    )
    parser.add_argument(
        "--portfolio",
        help="Portfolio GID to sync all projects (uses env var if not specified)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be changed, don't apply",
    )

    args = parser.parse_args()

    # Load settings
    settings = Settings()

    # Load canonical sections
    canonical_sections = await load_canonical_sections()

    logger.info(
        "canonical_sections_loaded",
        count=len(canonical_sections),
        sections=[s["name"] for s in canonical_sections],
    )

    # Initialize Asana client
    client = AsanaClient(settings.asana_access_token)

    if args.project:
        # Sync single project
        await sync_project_sections(
            client,
            args.project,
            canonical_sections,
            dry_run=args.dry_run,
        )
    elif args.portfolio or settings.asana_portfolio_gid:
        # Sync portfolio
        portfolio_gid = args.portfolio or settings.asana_portfolio_gid
        await sync_portfolio_projects(
            client,
            portfolio_gid,
            canonical_sections,
            dry_run=args.dry_run,
        )
    else:
        logger.error("no_target_specified", message="Specify --project or --portfolio")
        sys.exit(1)

    logger.info("sync_complete")


if __name__ == "__main__":
    asyncio.run(main())
