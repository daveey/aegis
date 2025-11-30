from typing import Any, Dict, Union, Optional

def format_asana_resource(resource: Union[Dict[str, Any], Any], resource_type: Optional[str] = None) -> str:
    """
    Formats an Asana resource for display.
    Format: Name [type:gid]

    Args:
        resource: The resource object or dictionary.
        resource_type: Optional type hint (e.g., 'task', 'project', 'user').
                       If not provided, tries to infer from resource_type attribute.

    Returns:
        Formatted string.
    """
    if not resource:
        return "None"

    name = "Unknown"
    gid = "Unknown"
    r_type = resource_type

    if isinstance(resource, dict):
        name = resource.get("name", "Unknown")
        gid = resource.get("gid", "Unknown")
        if not r_type:
            r_type = resource.get("resource_type")
    else:
        name = getattr(resource, "name", "Unknown")
        gid = getattr(resource, "gid", "Unknown")
        if not r_type:
            r_type = getattr(resource, "resource_type", None)

    type_code = "?"
    if r_type:
        r_type = r_type.lower()
        if r_type == "task":
            type_code = "t"
        elif r_type == "project":
            type_code = "p"
        elif r_type == "user":
            type_code = "u"
        elif r_type == "workspace":
            type_code = "w"
        elif r_type == "section":
            type_code = "s"
        elif r_type == "portfolio":
            type_code = "pf"
        elif r_type == "tag":
            type_code = "tg"
        else:
             type_code = r_type[0] if r_type else "?"

    return f"{name} [{type_code}:{gid}]"
