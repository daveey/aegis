#!/usr/bin/env python3
"""Setup Asana custom fields for Aegis swarm.

Creates the required custom fields in an Asana workspace:
- Agent (enum)
- Swarm Status (enum)
- Session ID (text)
- Cost (number)
- Max Cost (number)
- Merge Approval (enum)
- Worktree Path (text)
"""

import asyncio
import json
import sys
from pathlib import Path

import structlog

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import asana
from aegis.config import Settings

logger = structlog.get_logger()


async def load_custom_field_definitions() -> list[dict]:
    """Load custom field definitions from schema file.

    Returns:
        List of custom field definitions
    """
    schema_file = Path(__file__).parent.parent / "schema" / "asana_config.json"

    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    with open(schema_file) as f:
        schema = json.load(f)

    return schema["custom_fields"]


async def get_existing_custom_fields(workspace_gid: str, api_client: asana.ApiClient) -> dict[str, dict]:
    """Get existing custom fields in workspace.

    Args:
        workspace_gid: Workspace GID
        api_client: Asana API client

    Returns:
        Dict mapping field name to field data
    """
    custom_fields_api = asana.CustomFieldsApi(api_client)

    logger.info("fetching_existing_custom_fields", workspace_gid=workspace_gid)

    fields_generator = await asyncio.to_thread(
        custom_fields_api.get_custom_fields_for_workspace,
        workspace_gid,
        {"opt_fields": "name,gid,resource_subtype,enum_options.name"},
    )

    fields = {}
    for field in fields_generator:
        field_dict = field if isinstance(field, dict) else field.to_dict()
        fields[field_dict["name"]] = field_dict

    logger.info("existing_fields_fetched", count=len(fields))

    return fields


async def create_custom_field(
    workspace_gid: str,
    api_client: asana.ApiClient,
    field_def: dict,
    dry_run: bool = False,
) -> dict | None:
    """Create a custom field in workspace.

    Args:
        workspace_gid: Workspace GID
        api_client: Asana API client
        field_def: Field definition from schema
        dry_run: If True, only log without creating

    Returns:
        Created field data or None if dry run
    """
    custom_fields_api = asana.CustomFieldsApi(api_client)

    field_name = field_def["name"]
    field_type = field_def["type"]

    logger.info(
        "creating_custom_field",
        name=field_name,
        type=field_type,
        dry_run=dry_run,
    )

    if dry_run:
        print(f"  [DRY RUN] Would create: {field_name} ({field_type})")
        return None

    # Build request body
    body = {
        "data": {
            "name": field_name,
            "resource_subtype": field_type,
            "workspace": workspace_gid,
        }
    }

    # Add field-specific properties
    if field_type == "enum":
        # Add enum options
        enum_options = []
        for option in field_def.get("options", []):
            enum_options.append({"name": option["name"], "enabled": option.get("enabled", True)})

        body["data"]["enum_options"] = enum_options

    elif field_type == "number":
        body["data"]["precision"] = field_def.get("precision", 2)

    # Add description if provided
    if "description" in field_def:
        body["data"]["description"] = field_def["description"]

    try:
        field_response = await asyncio.to_thread(
            custom_fields_api.create_custom_field,
            body,
            {},
        )

        field_dict = field_response if isinstance(field_response, dict) else field_response.to_dict()

        logger.info(
            "custom_field_created",
            name=field_name,
            gid=field_dict.get("gid"),
        )

        print(f"  ✓ Created: {field_name} (GID: {field_dict.get('gid')})")

        return field_dict

    except Exception as e:
        logger.error(
            "custom_field_creation_failed",
            name=field_name,
            error=str(e),
        )
        print(f"  ✗ Failed to create {field_name}: {e}")
        return None


async def setup_custom_fields(
    workspace_gid: str,
    api_client: asana.ApiClient,
    dry_run: bool = False,
) -> None:
    """Setup all custom fields for Aegis.

    Args:
        workspace_gid: Workspace GID
        api_client: Asana API client
        dry_run: If True, only show what would be created
    """
    print(f"\n{'DRY RUN: ' if dry_run else ''}Setting up Aegis custom fields...\n")

    # Load field definitions
    field_definitions = await load_custom_field_definitions()
    print(f"Loaded {len(field_definitions)} field definition(s) from schema\n")

    # Get existing fields
    existing_fields = await get_existing_custom_fields(workspace_gid, api_client)
    print(f"Found {len(existing_fields)} existing custom field(s) in workspace\n")

    # Check which fields need to be created
    to_create = []
    already_exist = []

    for field_def in field_definitions:
        field_name = field_def["name"]
        if field_name in existing_fields:
            already_exist.append(field_name)
            print(f"  ✓ {field_name} already exists (GID: {existing_fields[field_name].get('gid')})")
        else:
            to_create.append(field_def)

    if already_exist:
        print(f"\n{len(already_exist)} field(s) already exist\n")

    if not to_create:
        print("✓ All custom fields already exist!\n")
        return

    print(f"\n{len(to_create)} field(s) need to be created:\n")

    # Create missing fields
    created = []
    for field_def in to_create:
        field_data = await create_custom_field(workspace_gid, api_client, field_def, dry_run=dry_run)
        if field_data:
            created.append(field_data)

    if not dry_run:
        print(f"\n✓ Created {len(created)} custom field(s)")
        print("\nNext steps:")
        print("  1. Run 'aegis sync --portfolio' to add sections to projects")
        print("  2. Set default values for fields in Asana workspace settings")
        print("  3. Start dispatcher with 'aegis start <project>'")
    else:
        print(f"\nDry run complete. Would create {len(to_create)} field(s).")
        print("Run without --dry-run to apply changes.")


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Setup Asana custom fields for Aegis")
    parser.add_argument(
        "--workspace",
        help="Workspace GID (uses env var if not specified)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show what would be created, don't apply",
    )

    args = parser.parse_args()

    try:
        # Load settings
        settings = Settings()

        workspace_gid = args.workspace or settings.asana_workspace_gid

        print(f"Workspace GID: {workspace_gid}")

        # Configure API client
        configuration = asana.Configuration()
        configuration.access_token = settings.asana_access_token
        api_client = asana.ApiClient(configuration)

        # Setup custom fields
        await setup_custom_fields(workspace_gid, api_client, dry_run=args.dry_run)

    except Exception as e:
        logger.error("setup_failed", error=str(e))
        print(f"\n✗ Setup failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
