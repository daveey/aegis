"""Tests for graceful shutdown handling."""

import asyncio
import contextlib
import signal
import subprocess
from unittest.mock import MagicMock, Mock

import pytest

from aegis.utils.shutdown import ShutdownHandler, get_shutdown_handler, shutdown_requested


class TestShutdownHandler:
    """Test cases for ShutdownHandler class."""

    def test_initialization(self):
        """Test shutdown handler initialization."""
        handler = ShutdownHandler(shutdown_timeout=60, subprocess_term_timeout=5)

        assert handler.shutdown_timeout == 60
        assert handler.subprocess_term_timeout == 5
        assert handler.shutdown_requested is False
        assert len(handler._cleanup_callbacks) == 0
        assert len(handler._in_progress_tasks) == 0
        assert len(handler._in_progress_subprocesses) == 0
        assert len(handler._active_sessions) == 0

    def test_register_cleanup_callback(self):
        """Test registering cleanup callbacks."""
        handler = ShutdownHandler()

        def cleanup_func():
            pass

        handler.register_cleanup_callback(cleanup_func)

        assert len(handler._cleanup_callbacks) == 1
        assert handler._cleanup_callbacks[0] == cleanup_func

    @pytest.mark.asyncio
    async def test_track_task(self):
        """Test tracking asyncio tasks."""
        handler = ShutdownHandler()

        async def dummy_task():
            await asyncio.sleep(0.1)

        task = asyncio.create_task(dummy_task())
        handler.track_task(task)

        assert task in handler._in_progress_tasks

        # Clean up
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_track_task_auto_removal(self):
        """Test that completed tasks are automatically removed from tracking."""
        handler = ShutdownHandler()

        async def dummy_task():
            await asyncio.sleep(0.01)

        task = asyncio.create_task(dummy_task())
        handler.track_task(task)

        assert task in handler._in_progress_tasks

        await task  # Wait for task to complete
        await asyncio.sleep(0.01)  # Give callback time to run

        assert task not in handler._in_progress_tasks

    def test_track_subprocess(self):
        """Test tracking subprocesses."""
        handler = ShutdownHandler()

        # Create a simple subprocess
        process = subprocess.Popen(["sleep", "0.1"])
        handler.track_subprocess(process)

        assert process.pid in handler._in_progress_subprocesses

        # Clean up
        process.terminate()
        process.wait()
        handler.untrack_subprocess(process)

    def test_untrack_subprocess(self):
        """Test untracking subprocesses."""
        handler = ShutdownHandler()

        process = subprocess.Popen(["sleep", "0.1"])
        handler.track_subprocess(process)
        handler.untrack_subprocess(process)

        assert process.pid not in handler._in_progress_subprocesses

        # Clean up
        process.terminate()
        process.wait()

    def test_track_session(self):
        """Test tracking database sessions."""
        handler = ShutdownHandler()

        mock_session = Mock()
        handler.track_session(mock_session)

        assert mock_session in handler._active_sessions

    def test_untrack_session(self):
        """Test untracking database sessions."""
        handler = ShutdownHandler()

        mock_session = Mock()
        handler.track_session(mock_session)
        handler.untrack_session(mock_session)

        assert mock_session not in handler._active_sessions

    def test_request_shutdown(self):
        """Test requesting shutdown."""
        handler = ShutdownHandler()

        assert handler.shutdown_requested is False

        handler.request_shutdown(signal.SIGINT)

        assert handler.shutdown_requested is True

    def test_request_shutdown_idempotent(self):
        """Test that multiple shutdown requests are handled gracefully."""
        handler = ShutdownHandler()

        handler.request_shutdown(signal.SIGINT)
        handler.request_shutdown(signal.SIGTERM)  # Should be ignored

        assert handler.shutdown_requested is True

    def test_install_signal_handlers(self):
        """Test installing signal handlers."""
        handler = ShutdownHandler()

        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        try:
            handler.install_signal_handlers()

            # Verify handlers were installed
            assert signal.getsignal(signal.SIGINT) == handler.request_shutdown
            assert signal.getsignal(signal.SIGTERM) == handler.request_shutdown

            # Verify originals were stored
            assert handler._original_sigint_handler == original_sigint
            assert handler._original_sigterm_handler == original_sigterm
        finally:
            # Restore original handlers
            handler.restore_signal_handlers()

    def test_restore_signal_handlers(self):
        """Test restoring signal handlers."""
        handler = ShutdownHandler()

        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        handler.install_signal_handlers()
        handler.restore_signal_handlers()

        # Verify handlers were restored
        assert signal.getsignal(signal.SIGINT) == original_sigint
        assert signal.getsignal(signal.SIGTERM) == original_sigterm

    @pytest.mark.asyncio
    async def test_wait_for_tasks_empty(self):
        """Test waiting for tasks when there are none."""
        handler = ShutdownHandler()

        result = await handler.wait_for_tasks()

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_tasks_completion(self):
        """Test waiting for tasks to complete."""
        handler = ShutdownHandler()

        async def quick_task():
            await asyncio.sleep(0.1)

        task = asyncio.create_task(quick_task())
        handler.track_task(task)

        result = await handler.wait_for_tasks()

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_tasks_timeout(self):
        """Test waiting for tasks with timeout."""
        handler = ShutdownHandler(shutdown_timeout=0.1)

        async def slow_task():
            await asyncio.sleep(10)

        task = asyncio.create_task(slow_task())
        handler.track_task(task)

        result = await handler.wait_for_tasks()

        assert result is False

        # Clean up
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    @pytest.mark.asyncio
    async def test_terminate_subprocesses_empty(self):
        """Test terminating subprocesses when there are none."""
        handler = ShutdownHandler()

        result = await handler.terminate_subprocesses()

        assert result is True

    @pytest.mark.asyncio
    async def test_terminate_subprocesses_graceful(self):
        """Test graceful subprocess termination."""
        handler = ShutdownHandler(subprocess_term_timeout=1)

        # Create a process that will exit quickly when sent SIGTERM
        process = subprocess.Popen(["sleep", "10"])
        handler.track_subprocess(process)

        result = await handler.terminate_subprocesses()

        assert result is True
        assert len(handler._in_progress_subprocesses) == 0

    @pytest.mark.asyncio
    async def test_terminate_subprocesses_force_kill(self):
        """Test force killing stubborn subprocesses."""
        handler = ShutdownHandler(subprocess_term_timeout=0.1)

        # Create a mock process that ignores SIGTERM
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Still running
        mock_process.terminate = MagicMock()
        mock_process.kill = MagicMock()

        handler._in_progress_subprocesses[12345] = mock_process

        result = await handler.terminate_subprocesses()

        assert result is False  # Not graceful
        assert mock_process.terminate.called
        assert mock_process.kill.called

    @pytest.mark.asyncio
    async def test_close_database_sessions(self):
        """Test closing database sessions."""
        handler = ShutdownHandler()

        mock_session1 = Mock()
        mock_session2 = Mock()

        handler.track_session(mock_session1)
        handler.track_session(mock_session2)

        await handler.close_database_sessions()

        mock_session1.close.assert_called_once()
        mock_session2.close.assert_called_once()
        assert len(handler._active_sessions) == 0

    @pytest.mark.asyncio
    async def test_close_database_sessions_with_errors(self):
        """Test closing database sessions when some fail."""
        handler = ShutdownHandler()

        mock_session1 = Mock()
        mock_session1.close.side_effect = Exception("Connection error")
        mock_session2 = Mock()

        handler.track_session(mock_session1)
        handler.track_session(mock_session2)

        # Should not raise exception
        await handler.close_database_sessions()

        mock_session1.close.assert_called_once()
        mock_session2.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_cleanup_callbacks_sync(self):
        """Test running synchronous cleanup callbacks."""
        handler = ShutdownHandler()

        callback_called = []

        def cleanup1():
            callback_called.append(1)

        def cleanup2():
            callback_called.append(2)

        handler.register_cleanup_callback(cleanup1)
        handler.register_cleanup_callback(cleanup2)

        await handler.run_cleanup_callbacks()

        assert callback_called == [1, 2]

    @pytest.mark.asyncio
    async def test_run_cleanup_callbacks_async(self):
        """Test running asynchronous cleanup callbacks."""
        handler = ShutdownHandler()

        callback_called = []

        async def cleanup1():
            callback_called.append(1)

        async def cleanup2():
            callback_called.append(2)

        handler.register_cleanup_callback(cleanup1)
        handler.register_cleanup_callback(cleanup2)

        await handler.run_cleanup_callbacks()

        assert callback_called == [1, 2]

    @pytest.mark.asyncio
    async def test_run_cleanup_callbacks_mixed(self):
        """Test running mixed sync and async cleanup callbacks."""
        handler = ShutdownHandler()

        callback_called = []

        def sync_cleanup():
            callback_called.append("sync")

        async def async_cleanup():
            callback_called.append("async")

        handler.register_cleanup_callback(sync_cleanup)
        handler.register_cleanup_callback(async_cleanup)

        await handler.run_cleanup_callbacks()

        assert callback_called == ["sync", "async"]

    @pytest.mark.asyncio
    async def test_run_cleanup_callbacks_with_errors(self):
        """Test that cleanup continues even if some callbacks fail."""
        handler = ShutdownHandler()

        callback_called = []

        def failing_cleanup():
            callback_called.append("failing")
            raise Exception("Cleanup error")

        def working_cleanup():
            callback_called.append("working")

        handler.register_cleanup_callback(failing_cleanup)
        handler.register_cleanup_callback(working_cleanup)

        # Should not raise exception
        await handler.run_cleanup_callbacks()

        assert "failing" in callback_called
        assert "working" in callback_called

    @pytest.mark.asyncio
    async def test_shutdown_sequence(self):
        """Test complete shutdown sequence."""
        handler = ShutdownHandler(shutdown_timeout=1, subprocess_term_timeout=1)

        # Set up some tasks and resources
        async def dummy_task():
            await asyncio.sleep(0.1)

        task = asyncio.create_task(dummy_task())
        handler.track_task(task)

        mock_session = Mock()
        handler.track_session(mock_session)

        callback_called = []

        def cleanup():
            callback_called.append(True)

        handler.register_cleanup_callback(cleanup)

        # Install handlers
        handler.install_signal_handlers()

        # Run shutdown
        await handler.shutdown()

        # Verify everything was cleaned up
        assert len(handler._in_progress_tasks) == 0
        assert len(handler._active_sessions) == 0
        assert len(handler._cleanup_callbacks) > 0  # Callbacks preserved
        assert callback_called == [True]

        # Note: Signal handlers are restored to their original values,
        # not set to None. In async test context, they may be set by pytest.


class TestShutdownHandlerGlobal:
    """Test cases for global shutdown handler functions."""

    def test_get_shutdown_handler_singleton(self):
        """Test that get_shutdown_handler returns singleton instance."""
        # Reset global state
        import aegis.utils.shutdown
        aegis.utils.shutdown._shutdown_handler = None

        handler1 = get_shutdown_handler()
        handler2 = get_shutdown_handler()

        assert handler1 is handler2

    def test_get_shutdown_handler_with_params(self):
        """Test creating shutdown handler with custom parameters."""
        # Reset global state
        import aegis.utils.shutdown
        aegis.utils.shutdown._shutdown_handler = None

        handler = get_shutdown_handler(shutdown_timeout=120, subprocess_term_timeout=20)

        assert handler.shutdown_timeout == 120
        assert handler.subprocess_term_timeout == 20

    def test_shutdown_requested_no_handler(self):
        """Test shutdown_requested when no handler exists."""
        # Reset global state
        import aegis.utils.shutdown
        aegis.utils.shutdown._shutdown_handler = None

        result = shutdown_requested()

        assert result is False

    def test_shutdown_requested_with_handler(self):
        """Test shutdown_requested with existing handler."""
        # Reset global state
        import aegis.utils.shutdown
        aegis.utils.shutdown._shutdown_handler = None

        handler = get_shutdown_handler()
        handler.request_shutdown()

        result = shutdown_requested()

        assert result is True
