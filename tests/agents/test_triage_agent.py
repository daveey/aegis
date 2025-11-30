"""Tests for Triage Agent."""

import pytest
from aegis.agents.triage import TriageAgent
from tests.agents.utils import AgentScenario, run_agent_scenario, verify_result


@pytest.fixture
def triage_agent(mock_agent_class):
    """Create a mocked TriageAgent."""
    MockTriageAgent = mock_agent_class(TriageAgent)
    return MockTriageAgent()


@pytest.mark.asyncio
class TestTriageAgent:
    """Tests for TriageAgent using scenarios."""

    async def test_route_to_planner(self, triage_agent, mock_task_factory):
        """Test routing to Planner when requirements are clear."""
        scenario = AgentScenario(
            name="Clear Requirements",
            task_input={
                "name": "Implement Login Feature",
                "notes": "Create a login page with email and password fields. Use JWT for authentication.",
            },
            llm_response="""
{
    "success": true,
    "next_agent": "Planner",
    "next_section": "Planning",
    "summary": "Requirements are clear",
    "details": ["Routing to Planner for architecture design"],
    "clear_session_id": true
}
""",
            expected_result={
                "success": True,
                "next_agent": "Planner",
                "next_section": "Planning",
                "summary_pattern": "Requirements are clear",
            }
        )

        result = await run_agent_scenario(triage_agent, scenario, mock_task_factory)
        verify_result(result, scenario.expected_result)

    async def test_request_clarification(self, triage_agent, mock_task_factory):
        """Test requesting clarification when requirements are vague."""
        scenario = AgentScenario(
            name="Vague Requirements",
            task_input={
                "name": "Fix the bug",
                "notes": "It's not working.",
            },
            llm_response="""
{
    "success": true,
    "next_agent": "Triage",
    "next_section": "Clarification Needed",
    "summary": "Task needs clarification",
    "details": ["What specifically is not working?", "Can you provide reproduction steps?"],
    "clear_session_id": false,
    "assignee": "me"
}
""",
            expected_result={
                "success": True,
                "next_agent": "Triage",
                "next_section": "Clarification Needed",
                "summary_pattern": "Task needs clarification",
                "details_pattern": "What specifically is not working",
            }
        )

        result = await run_agent_scenario(triage_agent, scenario, mock_task_factory)
        verify_result(result, scenario.expected_result)

    async def test_route_to_documentation(self, triage_agent, mock_task_factory):
        """Test routing to Documentation when it's a preference update."""
        scenario = AgentScenario(
            name="Update Preference",
            task_input={
                "name": "Use dark mode by default",
                "notes": "I prefer dark mode for all new UI components.",
            },
            llm_response="""
{
    "success": true,
    "next_agent": "Documentation",
    "next_section": "Ready Queue",
    "summary": "Preference to record: User prefers dark mode",
    "details": ["Routing to Documentation Agent"],
    "clear_session_id": true
}
""",
            expected_result={
                "success": True,
                "next_agent": "Documentation",
                "next_section": "Ready Queue",
                "summary_pattern": "Preference to record",
            }
        )

        result = await run_agent_scenario(triage_agent, scenario, mock_task_factory)
        verify_result(result, scenario.expected_result)
