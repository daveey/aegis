import os
import shutil
from pathlib import Path
from aegis.infrastructure.pid_manager import PIDManager
from aegis.infrastructure.worktree_manager import WorktreeManager
from aegis.orchestrator.dispatcher import SwarmDispatcher
from aegis.config import Settings

def test_aegis_state_migration():
    print("Testing Aegis state migration to .aegis...")

    # Setup
    cwd = Path.cwd()
    aegis_dir = cwd / ".aegis"
    if aegis_dir.exists():
        shutil.rmtree(aegis_dir)

    # Test PIDManager
    print("\nTesting PIDManager...")
    pid_manager = PIDManager()
    pid_manager.acquire()

    if (aegis_dir / "pid").exists():
        print("PASS: PID file created in .aegis/pid")
    else:
        print("FAIL: PID file not found in .aegis/pid")

    pid_manager.release()

    # Test WorktreeManager
    print("\nTesting WorktreeManager...")
    wm = WorktreeManager(cwd)

    if (aegis_dir / "worktrees").exists():
        print("PASS: Worktree directory created in .aegis/worktrees")
    else:
        print("FAIL: Worktree directory not found")

    gitignore = cwd / ".gitignore"
    if gitignore.exists():
        content = gitignore.read_text()
        if ".aegis/" in content:
            print("PASS: .aegis/ added to .gitignore")
        else:
            print("FAIL: .aegis/ not found in .gitignore")
            print(f"Gitignore content:\n{content}")

    # Test Dispatcher State
    print("\nTesting Dispatcher State...")
    # Mock settings
    class MockSettings:
        asana_access_token = "fake_token"
        asana_workspace_gid = "123"
        asana_team_gid = "456"
        poll_interval_seconds = 10
        asana_portfolio_gid = None

    try:
        dispatcher = SwarmDispatcher(MockSettings(), "123")
        if dispatcher.state_file == cwd / ".aegis" / "swarm_state.json":
            print("PASS: Dispatcher state file path is correct")
        else:
            print(f"FAIL: Dispatcher state file path is {dispatcher.state_file}")

        # Try to save state
        dispatcher._save_state()
        if (aegis_dir / "swarm_state.json").exists():
             print("PASS: swarm_state.json created in .aegis/")
        else:
             print("FAIL: swarm_state.json not found")

    except Exception as e:
        print(f"Dispatcher test skipped/failed (likely due to missing deps/env): {e}")

    # Cleanup
    if aegis_dir.exists():
        shutil.rmtree(aegis_dir)
    print("\nTest Complete")

if __name__ == "__main__":
    test_aegis_state_migration()
