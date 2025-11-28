"""Task orchestration and coordination.

Note: Old orchestrator (Orchestrator, TaskQueue, AgentPool) and prioritizer
have been deprecated and moved to _deprecated/.

New architecture uses SwarmDispatcher from aegis.orchestrator.dispatcher.
"""

from aegis.orchestrator.dispatcher import SwarmDispatcher  # noqa: F401

__all__ = ["SwarmDispatcher"]

# For backwards compatibility, try to import deprecated classes
try:
    from _deprecated.orchestrator_main import AgentPool, Orchestrator, TaskQueue  # noqa: F401
    from _deprecated.prioritizer import PriorityWeights, TaskPrioritizer, TaskScore  # noqa: F401

    __all__.extend([
        "Orchestrator",
        "TaskQueue",
        "AgentPool",
        "TaskPrioritizer",
        "PriorityWeights",
        "TaskScore",
    ])
except ImportError:
    # Deprecated modules not available
    pass
