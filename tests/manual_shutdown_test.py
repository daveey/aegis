#!/usr/bin/env python3
"""Manual test script for graceful shutdown handling.

This script demonstrates and tests the graceful shutdown functionality:
- Signal handlers (SIGINT/SIGTERM)
- Task completion waiting
- Subprocess termination
- Database session cleanup
- State saving

Usage:
    python tests/manual_shutdown_test.py [scenario]

Scenarios:
    quick     - Quick tasks that complete before shutdown (default)
    slow      - Slow tasks to test timeout behavior
    subprocess - Test subprocess handling and termination
    database  - Test database session cleanup
    all       - Run all scenarios

Press Ctrl+C during execution to test graceful shutdown.
"""

import asyncio
import subprocess
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import structlog

from aegis.database.session import cleanup_db_connections
from aegis.database.state import mark_orchestrator_stopped_async
from aegis.utils.shutdown import get_shutdown_handler

logger = structlog.get_logger(__name__)


async def test_quick_tasks():
    """Test scenario: Quick tasks that complete during shutdown."""
    print("\n=== Test Scenario: Quick Tasks ===")
    print("This tests that quick tasks complete gracefully during shutdown.")
    print("Press Ctrl+C within 5 seconds to test graceful shutdown.\n")

    shutdown_handler = get_shutdown_handler(shutdown_timeout=10)
    shutdown_handler.install_signal_handlers()

    # Register cleanup callbacks
    shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)
    shutdown_handler.register_cleanup_callback(cleanup_db_connections)

    async def quick_task(task_id: int):
        """Simulate a quick task."""
        print(f"Task {task_id}: Starting")
        for i in range(5):
            if shutdown_handler.shutdown_requested:
                print(f"Task {task_id}: Shutdown requested, wrapping up...")
                await asyncio.sleep(0.5)
                break
            await asyncio.sleep(1)
            print(f"Task {task_id}: Working... ({i+1}/5)")
        print(f"Task {task_id}: Completed")

    try:
        # Create and track tasks
        tasks = []
        for i in range(3):
            task = asyncio.create_task(quick_task(i + 1))
            shutdown_handler.track_task(task)
            tasks.append(task)

        # Wait for tasks or shutdown
        while not shutdown_handler.shutdown_requested:
            await asyncio.sleep(0.1)
            # Check if all tasks are done
            if all(t.done() for t in tasks):
                print("\nAll tasks completed naturally.")
                break

        if shutdown_handler.shutdown_requested:
            print("\nShutdown requested, waiting for tasks to complete...")
            await shutdown_handler.shutdown()
            print("Shutdown sequence completed successfully!")
        else:
            # Clean shutdown without interrupt
            await shutdown_handler.shutdown()
            print("Program completed normally.")

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt caught in main - shutdown handler will clean up")
        await shutdown_handler.shutdown()


async def test_slow_tasks():
    """Test scenario: Slow tasks to test timeout behavior."""
    print("\n=== Test Scenario: Slow Tasks (Timeout Test) ===")
    print("This tests timeout behavior when tasks don't complete in time.")
    print("Shutdown timeout set to 3 seconds.")
    print("Press Ctrl+C to test shutdown with long-running tasks.\n")

    shutdown_handler = get_shutdown_handler(shutdown_timeout=3)
    shutdown_handler.install_signal_handlers()
    shutdown_handler.register_cleanup_callback(mark_orchestrator_stopped_async)

    async def slow_task(task_id: int):
        """Simulate a very slow task."""
        print(f"Slow Task {task_id}: Starting (will take 30 seconds)")
        try:
            for i in range(30):
                await asyncio.sleep(1)
                print(f"Slow Task {task_id}: Still working... ({i+1}/30)")
        except asyncio.CancelledError:
            print(f"Slow Task {task_id}: Cancelled during shutdown")
            raise

    try:
        task = asyncio.create_task(slow_task(1))
        shutdown_handler.track_task(task)

        while not shutdown_handler.shutdown_requested:
            await asyncio.sleep(0.1)

        print("\nShutdown requested, will timeout after 3 seconds...")
        await shutdown_handler.shutdown()
        print("Shutdown completed (task may have been cancelled due to timeout)")

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt caught")
        await shutdown_handler.shutdown()


async def test_subprocess_handling():
    """Test scenario: Subprocess termination."""
    print("\n=== Test Scenario: Subprocess Handling ===")
    print("This tests graceful subprocess termination (SIGTERM then SIGKILL).")
    print("Press Ctrl+C to test subprocess cleanup.\n")

    shutdown_handler = get_shutdown_handler(
        shutdown_timeout=5,
        subprocess_term_timeout=2
    )
    shutdown_handler.install_signal_handlers()

    try:
        # Start a subprocess that will run for a while
        print("Starting subprocess: sleep 60")
        process = subprocess.Popen(["sleep", "60"])
        shutdown_handler.track_subprocess(process)
        print(f"Subprocess started with PID: {process.pid}")

        # Wait for interrupt
        while not shutdown_handler.shutdown_requested:
            await asyncio.sleep(0.5)
            if process.poll() is not None:
                print(f"Subprocess exited naturally with code: {process.returncode}")
                shutdown_handler.untrack_subprocess(process)
                break

        if shutdown_handler.shutdown_requested:
            print("\nShutdown requested, will terminate subprocess...")
            await shutdown_handler.shutdown()
            print("Subprocess terminated and shutdown completed!")

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt caught")
        await shutdown_handler.shutdown()


async def test_database_cleanup():
    """Test scenario: Database session cleanup."""
    print("\n=== Test Scenario: Database Session Cleanup ===")
    print("This tests that database sessions are properly closed during shutdown.")
    print("Press Ctrl+C to test session cleanup.\n")

    shutdown_handler = get_shutdown_handler()
    shutdown_handler.install_signal_handlers()
    shutdown_handler.register_cleanup_callback(cleanup_db_connections)

    try:
        # Create mock sessions (in real scenario these would be SQLAlchemy sessions)
        from unittest.mock import Mock

        sessions = []
        for i in range(3):
            session = Mock()
            session.close = Mock()
            sessions.append(session)
            shutdown_handler.track_session(session)
            print(f"Created and tracked session {i+1}")

        print("\nWaiting for interrupt... (Press Ctrl+C)")
        while not shutdown_handler.shutdown_requested:
            await asyncio.sleep(0.5)

        print("\nShutdown requested, closing sessions...")
        await shutdown_handler.shutdown()

        # Verify sessions were closed
        for i, session in enumerate(sessions):
            if session.close.called:
                print(f"Session {i+1}: Closed ✓")
            else:
                print(f"Session {i+1}: NOT CLOSED ✗")

    except KeyboardInterrupt:
        print("\nKeyboardInterrupt caught")
        await shutdown_handler.shutdown()


async def run_all_scenarios():
    """Run all test scenarios in sequence."""
    print("\n" + "="*60)
    print("Running All Shutdown Test Scenarios")
    print("="*60)

    scenarios = [
        ("Quick Tasks", test_quick_tasks),
        ("Slow Tasks", test_slow_tasks),
        ("Subprocess Handling", test_subprocess_handling),
        ("Database Cleanup", test_database_cleanup),
    ]

    for name, test_func in scenarios:
        print(f"\n\nStarting: {name}")
        print("-" * 60)
        try:
            await test_func()
            print(f"\n✓ {name} completed")
        except Exception as e:
            print(f"\n✗ {name} failed: {e}")

        # Small delay between tests
        await asyncio.sleep(2)

    print("\n" + "="*60)
    print("All scenarios completed!")
    print("="*60)


def print_usage():
    """Print usage information."""
    print(__doc__)


def main():
    """Main entry point."""
    scenario = sys.argv[1] if len(sys.argv) > 1 else "quick"

    scenarios = {
        "quick": test_quick_tasks,
        "slow": test_slow_tasks,
        "subprocess": test_subprocess_handling,
        "database": test_database_cleanup,
        "all": run_all_scenarios,
    }

    if scenario == "help" or scenario not in scenarios:
        print_usage()
        sys.exit(0 if scenario == "help" else 1)

    print("Graceful Shutdown Test Script")
    print("="*60)
    print(f"Scenario: {scenario}")
    print("="*60)

    try:
        asyncio.run(scenarios[scenario]())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)  # Standard exit code for SIGINT


if __name__ == "__main__":
    main()
