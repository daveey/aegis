import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from click.testing import CliRunner
from aegis.cli import main

@pytest.fixture
def mock_settings():
    with patch("aegis.cli.Settings") as MockSettings:
        settings = MockSettings.return_value
        settings.asana_access_token = "fake_token"
        yield settings

@pytest.fixture
def mock_asana_client():
    with patch("aegis.cli.AsanaClient") as MockClient:
        yield MockClient

@pytest.fixture
def mock_asana_service():
    with patch("aegis.cli.AsanaService") as MockService:
        service = MockService.return_value
        service.get_task = AsyncMock()
        service.get_task.return_value.name = "Test Task"
        yield service

@pytest.fixture
def mock_agents():
    with patch("aegis.cli.TriageAgent") as MockTriage, \
         patch("aegis.cli.PlannerAgent") as MockPlanner:

        MockTriage.return_value.name = "Triage Agent"
        MockTriage.return_value.execute = AsyncMock()
        MockTriage.return_value.execute.return_value.success = True
        MockTriage.return_value.execute.return_value.summary = "Success"
        MockTriage.return_value.execute.return_value.details = []

        yield {"Triage": MockTriage, "Planner": MockPlanner}

def test_agent_command_triage(mock_settings, mock_asana_client, mock_asana_service, mock_agents):
    runner = CliRunner()
    result = runner.invoke(main, ["agent", "Triage", "1234567890123456"])

    assert result.exit_code == 0
    assert "Running Triage Agent..." in result.output
    assert "Task GID: 1234567890123456" in result.output

    mock_agents["Triage"].assert_called_once()
    mock_agents["Triage"].return_value.execute.assert_called_once()

    # Check that interactive was False by default
    call_args = mock_agents["Triage"].return_value.execute.call_args
    assert call_args.kwargs.get("interactive") is False

def test_agent_command_interactive(mock_settings, mock_asana_client, mock_asana_service, mock_agents):
    runner = CliRunner()
    result = runner.invoke(main, ["agent", "Triage", "1234567890123456", "--interactive"])

    assert result.exit_code == 0
    assert "Entering interactive mode..." in result.output

    mock_agents["Triage"].return_value.execute.assert_called_once()

    # Check that interactive was True
    call_args = mock_agents["Triage"].return_value.execute.call_args
    assert call_args.kwargs.get("interactive") is True

def test_agent_command_url_resolution(mock_settings, mock_asana_client, mock_asana_service, mock_agents):
    runner = CliRunner()
    url = "https://app.asana.com/0/123/1234567890123456"
    result = runner.invoke(main, ["agent", "Triage", url])

    assert result.exit_code == 0
    assert "Task GID: 1234567890123456" in result.output

def test_agent_command_unknown_agent(mock_settings):
    runner = CliRunner()
    result = runner.invoke(main, ["agent", "UnknownAgent", "1234567890123456"])

    assert result.exit_code == 1
    assert "Unknown agent: UnknownAgent" in result.output
