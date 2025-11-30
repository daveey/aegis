import asyncio
import os
import sys
from pathlib import Path
import asana
from rich.console import Console

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from aegis.config import Settings

async def main():
    settings = Settings()
    configuration = asana.Configuration()
    configuration.access_token = settings.asana_access_token
    api_client = asana.ApiClient(configuration)
    custom_fields_api = asana.CustomFieldsApi(api_client)

    print(f"Inspecting custom fields in workspace: {settings.asana_workspace_gid}")

    # Get all custom fields
    fields = custom_fields_api.get_custom_fields_for_workspace(
        settings.asana_workspace_gid,
        {"opt_fields": "name,gid,type,resource_subtype,is_global_to_workspace,created_by"}
    )

    found = False
    for field in fields:
        if field["name"] == "Cost":
            print(f"\nFound 'Cost' field:")
            print(f"  GID: {field['gid']}")
            print(f"  Type: {field.get('type')}")
            print(f"  Resource Subtype: {field.get('resource_subtype')}")
            print(f"  Is Global: {field.get('is_global_to_workspace')}")
            print(f"  Created By: {field.get('created_by')}")
            found = True
        elif field["name"] == "Max Cost":
             print(f"\nFound 'Max Cost' field (for comparison):")
             print(f"  GID: {field['gid']}")
             print(f"  Type: {field.get('type')}")
             print(f"  Resource Subtype: {field.get('resource_subtype')}")

    if not found:
        print("\n'Cost' field not found in workspace.")

if __name__ == "__main__":
    asyncio.run(main())
