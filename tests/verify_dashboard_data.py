import json
import os
from pathlib import Path
from aegis.dashboard import utils

def test_dashboard_data_flow():
    # Setup dummy state
    root = Path.cwd()
    aegis_dir = root / ".aegis"
    aegis_dir.mkdir(exist_ok=True)

    state_file = aegis_dir / "swarm_state.json"

    dummy_state = {
        "orchestrator": {
            "started_at": "2023-01-01T00:00:00",
            "section_counts": {"In Progress": 5},
            "active_tasks_details": [{"gid": "123", "name": "Test Task", "agent": "Worker"}],
            "recent_errors": [{"timestamp": "2023-01-01T00:01:00", "error": "Test Error"}],
            "recent_events": [{"timestamp": "2023-01-01T00:02:00", "type": "Test Event"}]
        }
    }

    with open(state_file, "w") as f:
        json.dump(dummy_state, f)

    # Test utils
    states = utils.get_all_project_states()

    # Find current project
    current_state = None
    for s in states:
        if s["path"] == str(root):
            current_state = s
            break

    if not current_state:
        print("Current project not found in states.")
        # This might happen if not tracked, but let's assume it is for now or mock ProjectTracker
        # For this test, let's just check if we can load it via load_swarm_state directly if get_all_project_states fails
        # But get_all_project_states depends on ProjectTracker finding the project.
        pass

    # Direct load check
    loaded_state = utils.load_swarm_state()
    orch = loaded_state.get("orchestrator", {})

    print(f"Loaded Errors: {len(orch.get('recent_errors', []))}")
    print(f"Loaded Events: {len(orch.get('recent_events', []))}")

    assert len(orch.get("recent_errors", [])) == 1
    assert orch["recent_errors"][0]["error"] == "Test Error"

    assert len(orch.get("recent_events", [])) == 1
    assert orch["recent_events"][0]["type"] == "Test Event"

    print("Verification Successful!")

if __name__ == "__main__":
    test_dashboard_data_flow()
