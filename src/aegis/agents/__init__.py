"""Aegis swarm agents."""

from aegis.agents.base import AgentResult, BaseAgent
from aegis.agents.consolidator import ConsolidatorAgent
from aegis.agents.documentation import DocumentationAgent
from aegis.agents.ideation import IdeationAgent
from aegis.agents.merger import MergerAgent
from aegis.agents.planner import PlannerAgent
from aegis.agents.refactor import RefactorAgent
from aegis.agents.reviewer import ReviewerAgent
from aegis.agents.triage import TriageAgent
from aegis.agents.worker import WorkerAgent

__all__ = [
    "ConsolidatorAgent",
    "DocumentationAgent",
    "IdeationAgent",
    "MergerAgent",
    "PlannerAgent",
    "RefactorAgent",
    "ReviewerAgent",
    "TriageAgent",
    "WorkerAgent",
]
