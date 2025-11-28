"""Unit tests for SimpleExecutor agent."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from anthropic.types import Message, TextBlock, Usage

from aegis.agents.simple_executor import SimpleExecutor
from aegis.asana.models import AsanaTask, AsanaUser


@pytest.fixture
def mock_config():
    """Create a mock config object."""
    config = Mock()
    config.asana_access_token = "test_token"
    config.anthropic_api_key = "test_api_key"
    config.anthropic_model = "claude-sonnet-4-5-20250929"
    return config


@pytest.fixture
def mock_asana_client():
    """Create a mock Asana client."""
    client = AsyncMock()
    client.add_comment = AsyncMock()
    return client


@pytest.fixture
def mock_anthropic_client():
    """Create a mock Anthropic client."""
    client = Mock()
    return client


@pytest.fixture
def sample_task():
    """Create a sample Asana task."""
    return AsanaTask(
        gid="123456789",
        name="Build SimpleExecutor agent",
        notes="Create a simple executor that processes tasks using Claude API",
        completed=False,
        created_at=datetime.utcnow(),
        modified_at=datetime.utcnow(),
        assignee=AsanaUser(gid="user123", name="Test User"),
        due_on="2025-12-01",
    )


@pytest.fixture
def executor(mock_config, mock_asana_client, mock_anthropic_client):
    """Create a SimpleExecutor instance with mocked dependencies."""
    return SimpleExecutor(
        config=mock_config,
        asana_client=mock_asana_client,
        anthropic_client=mock_anthropic_client,
    )


class TestSimpleExecutorInit:
    """Tests for SimpleExecutor initialization."""

    def test_init_with_dependencies(self, mock_config, mock_asana_client, mock_anthropic_client):
        """Test initialization with provided dependencies."""
        executor = SimpleExecutor(
            config=mock_config,
            asana_client=mock_asana_client,
            anthropic_client=mock_anthropic_client,
        )
        assert executor.config == mock_config
        assert executor.asana_client == mock_asana_client
        assert executor.anthropic_client == mock_anthropic_client

    def test_init_creates_clients_if_not_provided(self):
        """Test that clients are created if not provided."""
        with patch("aegis.agents.simple_executor.Settings") as mock_settings, patch(
            "aegis.agents.simple_executor.AsanaClient"
        ) as mock_asana, patch("aegis.agents.simple_executor.Anthropic") as mock_anthropic:
            mock_settings.return_value.asana_access_token = "token"
            mock_settings.return_value.anthropic_api_key = "key"

            executor = SimpleExecutor()

            assert executor.config is not None
            mock_asana.assert_called_once()
            mock_anthropic.assert_called_once()


class TestPromptGeneration:
    """Tests for prompt generation."""

    def test_generate_prompt_basic(self, executor, sample_task):
        """Test basic prompt generation."""
        prompt = executor._generate_prompt(sample_task, "Aegis")

        assert "Task: Build SimpleExecutor agent" in prompt
        assert "Project: Aegis" in prompt
        assert "Create a simple executor that processes tasks using Claude API" in prompt
        assert "Due Date: 2025-12-01" in prompt

    def test_generate_prompt_with_code_path(self, executor, sample_task):
        """Test prompt generation with code path."""
        prompt = executor._generate_prompt(sample_task, "Aegis", code_path="/Users/test/code")

        assert "Code Location: /Users/test/code" in prompt

    def test_generate_prompt_without_notes(self, executor):
        """Test prompt generation for task without notes."""
        task = AsanaTask(
            gid="123",
            name="Simple Task",
            notes=None,
            completed=False,
            created_at=datetime.utcnow(),
            modified_at=datetime.utcnow(),
        )

        prompt = executor._generate_prompt(task, "Test Project")

        assert "Task: Simple Task" in prompt
        assert "Project: Test Project" in prompt
        assert "Task Description:" not in prompt

    def test_generate_prompt_includes_exit_instruction(self, executor, sample_task):
        """Test that prompt includes exit instruction."""
        prompt = executor._generate_prompt(sample_task, "Aegis")

        assert "IMPORTANT" in prompt
        assert "EXIT" in prompt


class TestClaudeAPICall:
    """Tests for Claude API calls."""

    @pytest.mark.asyncio
    async def test_call_claude_api_success(self, executor, mock_anthropic_client):
        """Test successful Claude API call."""
        # Create mock response with proper TextBlock
        text_block = TextBlock(text="I've completed the task successfully.", type="text")

        mock_response = Message(
            id="msg_123",
            content=[text_block],
            model="claude-sonnet-4-5-20250929",
            role="assistant",
            stop_reason="end_turn",
            type="message",
            usage=Usage(input_tokens=100, output_tokens=50),
        )

        mock_anthropic_client.messages.create = Mock(return_value=mock_response)

        # Call the method
        response_text, metadata = await executor._call_claude_api("Test prompt")

        # Verify response
        assert response_text == "I've completed the task successfully."
        assert metadata["input_tokens"] == 100
        assert metadata["output_tokens"] == 50
        assert metadata["model"] == "claude-sonnet-4-5-20250929"
        assert metadata["stop_reason"] == "end_turn"

        # Verify API was called correctly
        mock_anthropic_client.messages.create.assert_called_once()
        call_kwargs = mock_anthropic_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-5-20250929"
        assert call_kwargs["max_tokens"] == 4096
        assert call_kwargs["messages"][0]["content"] == "Test prompt"

    @pytest.mark.asyncio
    async def test_call_claude_api_error(self, executor, mock_anthropic_client):
        """Test Claude API call with error."""
        mock_anthropic_client.messages.create = Mock(
            side_effect=Exception("API connection failed")
        )

        with pytest.raises(Exception, match="API connection failed"):
            await executor._call_claude_api("Test prompt")


class TestPostResponse:
    """Tests for posting responses to Asana."""

    @pytest.mark.asyncio
    async def test_post_response_success(self, executor, mock_asana_client):
        """Test successful response posting."""
        from aegis.agents.formatters import TaskStatus

        await executor._post_response_to_asana("123", "Task completed!", TaskStatus.COMPLETE)

        # Verify comment was posted
        mock_asana_client.add_comment.assert_called_once()
        call_args = mock_asana_client.add_comment.call_args
        assert call_args[0][0] == "123"
        assert "Task completed!" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_post_response_with_split(self, executor, mock_asana_client):
        """Test posting response that needs to be split."""
        from aegis.agents.formatters import TaskStatus

        # Create a very long response that will be split
        long_response = "x" * 70000

        await executor._post_response_to_asana("123", long_response, TaskStatus.COMPLETE)

        # Verify multiple comments were posted (primary + continuation)
        assert mock_asana_client.add_comment.call_count >= 2

    @pytest.mark.asyncio
    async def test_post_response_retry_on_failure(self, executor, mock_asana_client):
        """Test that posting retries on failure."""
        from aegis.agents.formatters import TaskStatus

        # Fail twice, then succeed
        mock_asana_client.add_comment.side_effect = [
            Exception("Network error"),
            Exception("Network error"),
            None,
        ]

        await executor._post_response_to_asana("123", "Test", TaskStatus.COMPLETE)

        # Should have retried 3 times (2 failures + 1 success)
        assert mock_asana_client.add_comment.call_count == 3


class TestLogExecution:
    """Tests for execution logging."""

    def test_log_execution_success(self, executor):
        """Test logging successful execution."""
        started_at = datetime.utcnow()
        completed_at = datetime.utcnow()

        with patch("aegis.agents.simple_executor.get_db_session") as mock_session:
            mock_db_session = Mock()
            mock_session.return_value.__enter__.return_value = mock_db_session

            executor._log_execution(
                task_gid="123",
                status="completed",
                started_at=started_at,
                completed_at=completed_at,
                output="Task done!",
                metadata={"input_tokens": 100, "output_tokens": 50},
            )

            # Verify session operations
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called_once()

    def test_log_execution_failure(self, executor):
        """Test logging failed execution."""
        started_at = datetime.utcnow()
        completed_at = datetime.utcnow()

        with patch("aegis.agents.simple_executor.get_db_session") as mock_session:
            mock_db_session = Mock()
            mock_session.return_value.__enter__.return_value = mock_db_session

            executor._log_execution(
                task_gid="123",
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                error_message="Something went wrong",
                metadata={"traceback": "Error traceback..."},
            )

            # Verify session operations
            mock_db_session.add.assert_called_once()
            mock_db_session.commit.assert_called_once()

            # Verify TaskExecution was created with correct status
            task_execution = mock_db_session.add.call_args[0][0]
            assert task_execution.status == "failed"
            assert task_execution.success is False
            assert task_execution.error_message == "Something went wrong"


class TestExecuteTask:
    """Tests for the main execute_task method."""

    @pytest.mark.asyncio
    async def test_execute_task_success(self, executor, sample_task, mock_anthropic_client):
        """Test successful task execution end-to-end."""
        # Mock Claude API response
        text_block = TextBlock(text="I've completed the task successfully.", type="text")
        mock_response = Message(
            id="msg_123",
            content=[text_block],
            model="claude-sonnet-4-5-20250929",
            role="assistant",
            stop_reason="end_turn",
            type="message",
            usage=Usage(input_tokens=100, output_tokens=50),
        )
        mock_anthropic_client.messages.create = Mock(return_value=mock_response)

        # Mock database session
        with patch("aegis.agents.simple_executor.get_db_session") as mock_session:
            mock_db_session = Mock()
            mock_execution = Mock()
            mock_execution.id = 1
            mock_execution.duration_seconds = 5
            mock_db_session.add = Mock()
            mock_db_session.commit = Mock()
            mock_db_session.refresh = Mock()
            mock_session.return_value.__enter__.return_value = mock_db_session

            # Mock the execution object that gets added
            def mock_add(obj):
                obj.id = 1
                obj.duration_seconds = 5

            mock_db_session.add.side_effect = mock_add

            result = await executor.execute_task(sample_task, "Aegis", "/Users/test/code")

            # Verify result
            assert result["success"] is True
            assert result["output"] == "I've completed the task successfully."
            assert result["error"] is None
            assert "metadata" in result
            assert result["metadata"]["input_tokens"] == 100
            assert result["metadata"]["output_tokens"] == 50

            # Verify Asana comment was posted
            executor.asana_client.add_comment.assert_called()

    @pytest.mark.asyncio
    async def test_execute_task_api_failure(self, executor, sample_task, mock_anthropic_client):
        """Test task execution when Claude API fails."""
        # Mock API failure
        mock_anthropic_client.messages.create = Mock(
            side_effect=Exception("API connection failed")
        )

        # Mock database session
        with patch("aegis.agents.simple_executor.get_db_session") as mock_session:
            mock_db_session = Mock()
            mock_db_session.add = Mock()
            mock_db_session.commit = Mock()
            mock_db_session.refresh = Mock()
            mock_session.return_value.__enter__.return_value = mock_db_session

            def mock_add(obj):
                obj.id = 1
                obj.duration_seconds = 5

            mock_db_session.add.side_effect = mock_add

            result = await executor.execute_task(sample_task, "Aegis")

            # Verify result shows failure
            assert result["success"] is False
            assert result["error"] == "API connection failed"
            assert result["output"] is None

            # Verify error was posted to Asana
            executor.asana_client.add_comment.assert_called()

    @pytest.mark.asyncio
    async def test_execute_task_generates_correct_prompt(
        self, executor, sample_task, mock_anthropic_client
    ):
        """Test that execute_task generates the correct prompt."""
        # Mock Claude API response
        text_block = TextBlock(text="Task completed", type="text")
        mock_response = Message(
            id="msg_123",
            content=[text_block],
            model="claude-sonnet-4-5-20250929",
            role="assistant",
            stop_reason="end_turn",
            type="message",
            usage=Usage(input_tokens=100, output_tokens=50),
        )
        mock_anthropic_client.messages.create = Mock(return_value=mock_response)

        # Mock database
        with patch("aegis.agents.simple_executor.get_db_session") as mock_session:
            mock_db_session = Mock()
            mock_db_session.add = Mock()
            mock_db_session.commit = Mock()
            mock_db_session.refresh = Mock()
            mock_session.return_value.__enter__.return_value = mock_db_session

            def mock_add(obj):
                obj.id = 1

            mock_db_session.add.side_effect = mock_add

            await executor.execute_task(sample_task, "Aegis", "/Users/test/code")

            # Check that API was called with correct prompt
            call_kwargs = mock_anthropic_client.messages.create.call_args[1]
            prompt = call_kwargs["messages"][0]["content"]

            assert "Task: Build SimpleExecutor agent" in prompt
            assert "Project: Aegis" in prompt
            assert "Code Location: /Users/test/code" in prompt
            assert sample_task.notes in prompt
