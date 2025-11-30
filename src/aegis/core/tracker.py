"""Project tracking management."""

import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel


class TrackedProject(BaseModel):
    """Model for a tracked project."""

    gid: str
    name: str
    local_path: str
    added_at: str


class ProjectTracker:
    """Manages tracked projects."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize tracker.

        Args:
            config_dir: Directory to store config. Defaults to ~/.aegis
        """
        if config_dir:
            self.config_dir = config_dir
        else:
            # Prefer local .aegis directory if it exists or if we are initializing
            local_aegis = Path.cwd() / ".aegis"
            if local_aegis.exists():
                self.config_dir = local_aegis
            else:
                self.config_dir = Path.home() / ".aegis"

        self.projects_file = self.config_dir / "projects.yaml"
        self._ensure_config_dir()

    def _ensure_config_dir(self):
        """Ensure configuration directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _load_projects(self) -> Dict[str, dict]:
        """Load projects from file."""
        if not self.projects_file.exists():
            return {}

        try:
            with open(self.projects_file) as f:
                return yaml.safe_load(f) or {}
        except yaml.YAMLError:
            return {}

    def _save_projects(self, projects: Dict[str, dict]):
        """Save projects to file."""
        with open(self.projects_file, "w") as f:
            yaml.safe_dump(projects, f)

    def add_project(self, gid: str, name: str, local_path: str | Path):
        """Add a project to tracking.

        Args:
            gid: Asana Project GID
            name: Project Name
            local_path: Local filesystem path
        """
        from datetime import datetime

        projects = self._load_projects()

        projects[gid] = {
            "gid": gid,
            "name": name,
            "local_path": str(local_path),
            "added_at": datetime.now().isoformat()
        }

        self._save_projects(projects)

    def get_projects(self) -> List[dict]:
        """Get all tracked projects.

        Returns:
            List of project dictionaries
        """
        projects = self._load_projects()
        return list(projects.values())

    def get_project(self, gid: str) -> Optional[dict]:
        """Get a specific project by GID."""
        projects = self._load_projects()
        return projects.get(gid)

    def find_by_path(self, path: str | Path) -> Optional[dict]:
        """Find a project by local path."""
        path_str = str(path)
        projects = self._load_projects()
        for p in projects.values():
            if p["local_path"] == path_str:
                return p
        return None

    def remove_project(self, gid: str):
        """Remove a project from tracking."""
        projects = self._load_projects()
        if gid in projects:
            del projects[gid]
            self._save_projects(projects)
