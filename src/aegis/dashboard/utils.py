import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import os

from aegis.core.tracker import ProjectTracker

def get_project_root() -> Path:
    """Get the root directory of the current project."""
    # Assuming we are running from the project root or a subdirectory
    # This might need to be more robust, but for now let's assume CWD is project root
    # or we can find .aegis directory
    cwd = Path.cwd()
    if (cwd / ".aegis").exists():
        return cwd

    # Traverse up
    for parent in cwd.parents:
        if (parent / ".aegis").exists():
            return parent

    return cwd

def load_swarm_state() -> Dict[str, Any]:
    """Load the swarm state from .aegis/swarm_state.json."""
    root = get_project_root()
    state_file = root / ".aegis" / "swarm_state.json"

    if not state_file.exists():
        return {}

    try:
        with open(state_file, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def get_all_project_states() -> List[Dict[str, Any]]:
    """Get state for all tracked projects."""
    root = get_project_root()
    tracker = ProjectTracker(config_dir=root / ".aegis")
    projects = tracker.get_projects()
    states = []

    for p in projects:
        path = Path(p["local_path"])
        state_file = path / ".aegis" / "swarm_state.json"

        project_state = {
            "gid": p["gid"],
            "name": p["name"],
            "path": str(path),
            "state": {},
            "is_running": False
        }

        # Check if running
        pid_file = path / ".aegis" / "pids" / f"{p['gid']}.pid"
        if pid_file.exists():
             # Verify PID is actually running?
             # For dashboard speed, maybe just check file existence for now
             # or use PIDManager if we want to be sure, but that might be slow
             project_state["is_running"] = True

        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    project_state["state"] = json.load(f)
            except Exception:
                pass

        states.append(project_state)

    return states

def load_swarm_memory(project_path: Path = None) -> str:
    """Load the swarm memory from .aegis/swarm_memory.md."""
    root = project_path if project_path else get_project_root()
    memory_file = root / ".aegis" / "swarm_memory.md"

    if not memory_file.exists():
        return "No memory file found."

    try:
        with open(memory_file, "r") as f:
            return f.read()
    except Exception:
        return "Error reading memory file."

def get_active_tasks(state: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """Get list of active tasks from all projects.

    Returns:
        List of dicts with task details (gid, name, agent, section, project_name, etc.)
    """
    all_tasks = []

    # If state is passed (legacy single project mode), use it
    if state:
        orch = state.get("orchestrator", {})
        details = orch.get("active_tasks_details", [])
        if not details:
            # Fallback to GID list
            gids = orch.get("active_tasks", [])
            for gid in gids:
                all_tasks.append({
                    "gid": gid,
                    "name": "Unknown Task",
                    "agent": "Unknown",
                    "section": "Unknown",
                    "project_name": "Current Project"
                })
        else:
            for task in details:
                task["project_name"] = "Current Project"
                all_tasks.append(task)
        return all_tasks

    # Otherwise fetch from all projects
    project_states = get_all_project_states()
    seen_gids = set()

    for p in project_states:
        orch = p["state"].get("orchestrator", {})
        details = orch.get("active_tasks_details", [])

        if details:
            for task in details:
                gid = task.get("gid")
                if gid and gid in seen_gids:
                    continue
                if gid:
                    seen_gids.add(gid)

                task["project_name"] = p["name"]
                task["project_gid"] = p["gid"]
                all_tasks.append(task)
        else:
            # Fallback
            gids = orch.get("active_tasks", [])
            for gid in gids:
                 if gid in seen_gids:
                     continue
                 seen_gids.add(gid)

                 all_tasks.append({
                    "gid": gid,
                    "name": "Unknown Task",
                    "agent": "Unknown",
                    "section": "Unknown",
                    "project_name": p["name"],
                    "project_gid": p["gid"]
                })

    return all_tasks

def get_tasks_per_section() -> List[Dict[str, Any]]:
    """Get tasks per section for all projects."""
    project_states = get_all_project_states()
    data = []

    for p in project_states:
        orch = p["state"].get("orchestrator", {})
        counts = orch.get("section_counts", {})

        for section, count in counts.items():
            data.append({
                "project_name": p["name"],
                "section": section,
                "count": count
            })

    return data

def get_recent_logs(limit: int = 50) -> List[str]:
    """Get the most recent log lines from the main log file."""
    root = get_project_root()
    log_file = root / "logs" / "aegis.log" # Assuming this is the main log

    # If not found, try to find any log file in logs/
    if not log_file.exists():
        log_dir = root / "logs"
        if log_dir.exists():
            logs = list(log_dir.glob("*.log"))
            if logs:
                # Sort by modification time
                logs.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                log_file = logs[0]
            else:
                return ["No log files found."]
        else:
            return ["Logs directory not found."]

    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            return lines[-limit:]
    except Exception as e:
        return [f"Error reading logs: {e}"]

def get_session_log(session_id: str, project_path: Path = None) -> str:
    """Get the log content for a specific session."""
    root = project_path if project_path else get_project_root()
    log_dir = root / "logs" / "sessions"

    if not log_dir.exists():
        return "Session logs directory not found."

    # Look for file with session_id
    # Assuming format like {timestamp}_{session_id}.log or just {session_id}.log
    # Let's search for *{session_id}*.log
    matches = list(log_dir.glob(f"*{session_id}*.log"))

    if not matches:
        return f"No log found for session {session_id}"

    try:
        with open(matches[0], "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading session log: {e}"


def get_env_path() -> Path:
    """Get the path to the .env file."""
    return get_project_root() / ".env"


def read_env_file() -> str:
    """Read the content of the .env file."""
    env_path = get_env_path()
    if not env_path.exists():
        return ""
    try:
        with open(env_path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading .env file: {e}"


def write_env_file(content: str) -> bool:
    """Write content to the .env file."""
    env_path = get_env_path()
    try:
        with open(env_path, "w") as f:
            f.write(content)
        return True
    except Exception:
        return False


def get_prompts_dir() -> Path:
    """Get the path to the prompts directory."""
    return get_project_root() / "prompts"


def list_prompt_files() -> List[str]:
    """List all prompt files in the prompts directory."""
    prompts_dir = get_prompts_dir()
    if not prompts_dir.exists():
        return []
    return [f.name for f in prompts_dir.glob("*.txt")]


def read_prompt_file(filename: str) -> str:
    """Read the content of a prompt file."""
    prompts_dir = get_prompts_dir()
    file_path = prompts_dir / filename
    if not file_path.exists():
        return ""
    try:
        with open(file_path, "r") as f:
            return f.read()
    except Exception as e:
        return f"Error reading prompt file: {e}"


def write_prompt_file(filename: str, content: str) -> bool:
    """Write content to a prompt file."""
    prompts_dir = get_prompts_dir()
    file_path = prompts_dir / filename
    try:
        with open(file_path, "w") as f:
            f.write(content)
        return True
    except Exception:
        return False

def get_project_errors(project_gid: str) -> List[Dict[str, Any]]:
    """Get recent errors for a project."""
    states = get_all_project_states()
    for p in states:
        if p["gid"] == project_gid:
            return p["state"].get("orchestrator", {}).get("recent_errors", [])
    return []

def get_project_events(project_gid: str) -> List[Dict[str, Any]]:
    """Get recent events for a project."""
    states = get_all_project_states()
    for p in states:
        if p["gid"] == project_gid:
            return p["state"].get("orchestrator", {}).get("recent_events", [])
    return []

def get_global_activity_feed(limit: int = 20) -> List[Dict[str, Any]]:
    """Get a consolidated list of recent events from all projects."""
    states = get_all_project_states()
    all_events = []
    seen_events = set()

    for p in states:
        events = p["state"].get("orchestrator", {}).get("recent_events", [])
        for evt in events:
            # Create a signature for deduplication
            # We exclude project_name since that's added by us
            sig = (evt.get("timestamp"), evt.get("type"), json.dumps(evt.get("details", {}), sort_keys=True))

            if sig in seen_events:
                continue

            seen_events.add(sig)

            # Add project name to event for context
            evt_copy = evt.copy()
            evt_copy["project_name"] = p["name"]
            all_events.append(evt_copy)

    # Sort by timestamp (assuming timestamp is ISO string or comparable)
    # If timestamp format varies, we might need more robust parsing
    try:
        all_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    except Exception:
        pass # Best effort sort

    return all_events[:limit]

def get_syncer_info(project_path: str) -> Dict[str, Any]:
    """Get syncer session info for a project."""
    try:
        path = Path(project_path)
        info_file = path / ".aegis" / "syncer_info.json"
        if info_file.exists():
            with open(info_file, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}
