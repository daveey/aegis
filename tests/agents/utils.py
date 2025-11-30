"""Utilities for agent testing."""

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional, Union

from aegis.agents.base import AgentResult, BaseAgent
from aegis.asana.models import AsanaTask, AsanaProject, AsanaUser


@dataclass
class AgentScenario:
    """A test scenario for an agent."""

    name: str
    task_input: dict[str, Any]
    llm_response: str
    expected_result: dict[str, Any]
    interactive: bool = False

    # Optional overrides for task attributes
    task_overrides: dict[str, Any] = field(default_factory=dict)


async def run_agent_scenario(
    agent: BaseAgent,
    scenario: AgentScenario,
    mock_task_factory,
) -> AgentResult:
    """Run an agent scenario.

    Args:
        agent: The agent instance to test.
        scenario: The scenario definition.
        mock_task_factory: Fixture to create a mock task.

    Returns:
        The result from the agent execution.
    """
    # Create task from input
    task_data = scenario.task_input.copy()
    task_data.update(scenario.task_overrides)
    task = mock_task_factory(**task_data)

    # Mock the LLM response on the agent
    # We assume the agent has been patched with a mock runner or we patch it here
    # For this implementation, we'll assume the agent's run_claude_code method
    # can be mocked or intercepted.

    # However, since we are using a real agent instance in tests, we need a way to
    # inject the response. The cleanest way is if the agent fixture handles this,
    # or if we patch the method on the instance.

    # Let's rely on the `mock_agent_runner` fixture to have been applied to the agent
    # or the environment. But here we need to set the specific response for this scenario.

    if hasattr(agent, "set_mock_response"):
        agent.set_mock_response(scenario.llm_response)
    else:
        # Fallback if the agent isn't a mock mixin
        raise ValueError("Agent must support set_mock_response for scenario testing")

    # Execute agent
    result = await agent.execute(task, interactive=scenario.interactive)

    return result


def verify_result(result: AgentResult, expected: dict[str, Any]):
    """Verify agent result matches expectations."""

    # Check success status
    if "success" in expected:
        assert result.success == expected["success"], \
            f"Expected success={expected['success']}, got {result.success}. Error: {result.error}"

    # Check next agent
    if "next_agent" in expected:
        assert result.next_agent == expected["next_agent"], \
            f"Expected next_agent={expected['next_agent']}, got {result.next_agent}"

    # Check next section
    if "next_section" in expected:
        assert result.next_section == expected["next_section"], \
            f"Expected next_section={expected['next_section']}, got {result.next_section}"

    # Check summary (partial match)
    if "summary_pattern" in expected:
        pattern = expected["summary_pattern"]
        assert re.search(pattern, result.summary, re.IGNORECASE), \
            f"Summary '{result.summary}' did not match pattern '{pattern}'"

    # Check details (partial match on any detail)
    if "details_pattern" in expected:
        pattern = expected["details_pattern"]
        found = any(re.search(pattern, d, re.IGNORECASE) for d in result.details)
        assert found, f"No detail matched pattern '{pattern}'. Details: {result.details}"
