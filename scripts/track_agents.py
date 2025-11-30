import asyncio
from pathlib import Path
from aegis.core.tracker import ProjectTracker

async def track_agents_project():
    tracker = ProjectTracker()

    # Project: Agents
    gid = "1212155091370091"
    name = "Agents"
    cwd = Path.cwd()

    print(f"Tracking project '{name}' ({gid}) at {cwd}")
    tracker.add_project(gid, name, cwd)
    print("Successfully added to tracking.")

if __name__ == "__main__":
    asyncio.run(track_agents_project())
