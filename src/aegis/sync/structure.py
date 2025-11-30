"""Sync Asana project sections and custom fields to match canonical structure.

This module enforces the canonical configuration defined in schema/asana_config.json.
It creates missing sections, reorders them, and ensures required custom fields are added.
"""

import asyncio
import json
from pathlib import Path

import structlog
from aegis.asana.client import AsanaClient

logger = structlog.get_logger()


async def load_schema() -> dict:
    """Load full schema from file.

    Returns:
        Dict containing canonical_sections and custom_fields
    """
    # Adjust path to find schema from src/aegis/sync/structure.py
    # root is 3 levels up: sync -> aegis -> src -> root
    schema_file = Path(__file__).parents[3] / "schema" / "asana_config.json"

    if not schema_file.exists():
        # Fallback for when installed as package or different structure
        # Try to find relative to package root
        import aegis
        package_root = Path(aegis.__file__).parent.parent.parent
        schema_file = package_root / "schema" / "asana_config.json"

        if not schema_file.exists():
             raise FileNotFoundError(f"Schema file not found: {schema_file}")

    with open(schema_file) as f:
        schema = json.load(f)

    return schema


async def get_workspace_custom_fields(client: AsanaClient, workspace_gid: str) -> dict[str, str]:
    """Get mapping of custom field names to GIDs in the workspace.

    Args:
        client: AsanaClient instance
        workspace_gid: Workspace GID

    Returns:
        Dict mapping field name to GID
    """
    custom_fields_api = client.custom_fields_api

    fields_generator = await asyncio.to_thread(
        custom_fields_api.get_custom_fields_for_workspace,
        workspace_gid,
        {"opt_fields": "name,gid"},
    )

    fields = {}
    for field in fields_generator:
        field_dict = field if isinstance(field, dict) else field.to_dict()
        fields[field_dict["name"]] = field_dict["gid"]

    return fields


async def sync_project_custom_fields(
    client: AsanaClient,
    project_gid: str,
    required_fields: list[dict],
    workspace_fields: dict[str, str],
    dry_run: bool = False,
) -> None:
    """Ensure project has all required custom fields.

    Args:
        client: AsanaClient instance
        project_gid: Project GID
        required_fields: List of custom field definitions from schema
        workspace_fields: Dict mapping field name to GID in workspace
        dry_run: If True, only log changes
    """
    logger.info("syncing_custom_fields", project_gid=project_gid)

    # Get project's current custom fields
    settings_response = await asyncio.to_thread(
        client.custom_field_settings_api.get_custom_field_settings_for_project,
        project_gid,
        {"opt_fields": "custom_field.name,custom_field.gid"},
    )

    current_field_gids = set()
    for setting in settings_response:
        setting_dict = setting if isinstance(setting, dict) else setting.to_dict()
        if setting_dict.get("custom_field"):
            current_field_gids.add(setting_dict["custom_field"]["gid"])

    # Check each required field
    for field_def in required_fields:
        field_name = field_def["name"]

        if field_name not in workspace_fields:
            logger.warning("custom_field_not_found_in_workspace", field_name=field_name)
            continue

        field_gid = workspace_fields[field_name]

        if field_gid not in current_field_gids:
            if not dry_run:
                try:
                    await client.add_custom_field_to_project(project_gid, field_gid)
                    logger.info("added_custom_field", project_gid=project_gid, field_name=field_name)
                except Exception as e:
                    logger.error("failed_to_add_custom_field", field_name=field_name, error=str(e))
            else:
                logger.info("would_add_custom_field", field_name=field_name)
        else:
            logger.debug("custom_field_already_present", field_name=field_name)


async def sync_project_structure(
    client: AsanaClient,
    project_gid: str,
    schema: dict,
    workspace_fields: dict[str, str],
    dry_run: bool = False,
) -> None:
    """Sync sections and custom fields for a single project.

    Args:
        client: AsanaClient instance
        project_gid: Project GID
        schema: Full schema dict
        workspace_fields: Dict mapping field name to GID
        dry_run: If True, only log changes
    """
    logger.info("syncing_project_structure", project_gid=project_gid, dry_run=dry_run)

    # 1. Sync Sections
    canonical_sections = schema["canonical_sections"]
    current_sections = await client.get_sections(project_gid)
    current_section_names = [s.name for s in current_sections]

    canonical_names = [s["name"] for s in canonical_sections]
    missing_sections = [name for name in canonical_names if name not in current_section_names]

    if missing_sections:
        logger.info("creating_missing_sections", sections=missing_sections)
        for section_name in missing_sections:
            if not dry_run:
                try:
                    await client.create_section(project_gid, section_name)
                    logger.info("section_created", section_name=section_name)
                except Exception as e:
                    logger.error("section_creation_failed", section_name=section_name, error=str(e))
            else:
                logger.info("would_create_section", section_name=section_name)

    # 1.5 Reorder Sections
    # Refresh sections to get new GIDs and current order
    current_sections = await client.get_sections(project_gid)
    section_map = {s.name: s for s in current_sections}
    current_gids = [s.gid for s in current_sections]

    previous_gid = None

    for section_def in canonical_sections:
        section_name = section_def["name"]
        if section_name not in section_map:
            continue

        section_gid = section_map[section_name].gid

        should_move = False

        if previous_gid is None:
            # Should be first
            if current_gids[0] != section_gid:
                should_move = True
        else:
            # Should be after previous_gid
            try:
                prev_index = current_gids.index(previous_gid)
                curr_index = current_gids.index(section_gid)
                if curr_index != prev_index + 1:
                    should_move = True
            except ValueError:
                should_move = True

        if should_move:
            if not dry_run:
                try:
                    await client.reorder_section(
                        project_gid,
                        section_gid,
                        after_section_gid=previous_gid
                    )
                    logger.info("reordered_section", section_name=section_name, after=previous_gid)

                    # Update local list to reflect change for next iteration
                    current_gids.remove(section_gid)
                    if previous_gid is None:
                        current_gids.insert(0, section_gid)
                    else:
                        prev_index = current_gids.index(previous_gid)
                        current_gids.insert(prev_index + 1, section_gid)

                except Exception as e:
                    logger.error("reorder_failed", section_name=section_name, error=str(e))
            else:
                logger.info("would_reorder_section", section_name=section_name, after=previous_gid)

        previous_gid = section_gid

    # 2. Sync Custom Fields
    await sync_project_custom_fields(
        client,
        project_gid,
        schema["custom_fields"],
        workspace_fields,
        dry_run=dry_run
    )

    logger.info("project_structure_sync_complete", project_gid=project_gid)
