#!/usr/bin/env python3
"""Test script to verify log file creation in orchestrator."""

import asyncio
from pathlib import Path

from aegis.config import Settings
from aegis.orchestrator.main import Orchestrator


async def test_log_files():
    """Test that log files are created for task executions."""

    print("=" * 60)
    print("Testing Log File Creation")
    print("=" * 60)

    # Load configuration
    settings = Settings()

    # Get Aegis project GID
    project_gid = "1212085431574340"  # Aegis project
    project_name = "Aegis"

    print(f"\nProject: {project_name} ({project_gid})")
    print(f"Max concurrent tasks: {settings.max_concurrent_tasks}")
    print(f"Execution mode: {settings.execution_mode}")

    # Check logs directory
    logs_dir = Path("logs")
    print(f"\nLogs directory: {logs_dir.absolute()}")
    print(f"Logs directory exists: {logs_dir.exists()}")

    if logs_dir.exists():
        existing_logs = list(logs_dir.glob("task_*.log"))
        print(f"Existing task logs: {len(existing_logs)}")
        if existing_logs:
            print("\nRecent task logs:")
            for log_file in sorted(existing_logs, key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
                size = log_file.stat().st_size
                print(f"  - {log_file.name} ({size} bytes)")

    # Create orchestrator with web dashboard
    print("\n" + "=" * 60)
    print("Creating orchestrator...")
    orchestrator = Orchestrator(
        settings=settings,
        project_gid=project_gid,
        project_name=project_name,
        use_live_display=False,  # No display for testing
        enable_web=True,
        web_port=8000,
    )

    print("✓ Orchestrator created successfully")
    print("✓ Web dashboard URL: http://127.0.0.1:8000")

    # Run for 45 seconds to test task execution and log creation
    print("\n" + "=" * 60)
    print("Running orchestrator for 45 seconds...")
    print("This will:")
    print("  1. Poll for tasks from Asana")
    print("  2. Execute ready tasks")
    print("  3. Create log files for each execution")
    print("  4. Web dashboard will be available")
    print("\nPress Ctrl+C to stop early")
    print("=" * 60 + "\n")

    try:
        await asyncio.wait_for(orchestrator.run(), timeout=45)
    except TimeoutError:
        print("\n✓ Test timeout reached")
    except KeyboardInterrupt:
        print("\n✓ Interrupted by user")
    finally:
        # Check for new log files
        print("\n" + "=" * 60)
        print("Checking for newly created log files...")
        print("=" * 60)

        if logs_dir.exists():
            new_logs = list(logs_dir.glob("task_*.log"))
            print(f"\nTotal task logs: {len(new_logs)}")

            if new_logs:
                print("\nTask logs (newest first):")
                for log_file in sorted(new_logs, key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
                    size = log_file.stat().st_size
                    mtime = log_file.stat().st_mtime
                    from datetime import datetime
                    timestamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    print(f"  - {log_file.name}")
                    print(f"    Size: {size} bytes")
                    print(f"    Modified: {timestamp}")

                    # Show first few lines
                    if size > 0:
                        with open(log_file) as f:
                            lines = f.readlines()[:5]
                            print("    Preview:")
                            for line in lines:
                                print(f"      {line.rstrip()}")
                    print()

        print("=" * 60)
        print("Test Complete")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_log_files())
