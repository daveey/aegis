import sys
from pathlib import Path
import json

# Add src to path
sys.path.append(str(Path.cwd() / "src"))

from aegis.dashboard import utils

def verify_data():
    print("Loading project states...")
    states = utils.get_all_project_states()
    print(f"Found {len(states)} projects.")

    for p in states:
        print(f"\nProject: {p['name']} ({p['gid']})")
        print(f"  Running: {p['is_running']}")
        print(f"  State keys: {list(p['state'].keys())}")

        orch = p['state'].get('orchestrator', {})
        print(f"  Orchestrator keys: {list(orch.keys())}")
        print(f"  Active Tasks: {len(orch.get('active_tasks_details', []))}")
        print(f"  Recent Errors: {len(orch.get('recent_errors', []))}")
        print(f"  Recent Events: {len(orch.get('recent_events', []))}")
        print(f"  Section Counts: {orch.get('section_counts', {})}")

if __name__ == "__main__":
    verify_data()
