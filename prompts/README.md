# Agent Prompts

This directory contains system prompts for each agent in the Aegis swarm.

## Prompt Structure

Each prompt should:
1. Define the agent's role and capabilities
2. Specify expected outputs and format
3. Include context about the swarm system
4. Reference available tools and constraints

## Available Prompts

- **`triage.md`** - Triage Agent (Requirements Analyst)
- **`planner.md`** - Planner Agent (Architect)
- **`worker.md`** - Worker Agent (Builder)
- **`reviewer.md`** - Reviewer Agent (Gatekeeper)
- **`merger.md`** - Merger Agent (Integrator)
- **`documentation.md`** - Documentation Agent (Librarian)
- **`watchdog.md`** - Watchdog Agent (Supervisor)

## Using Prompts

Prompts are loaded by agents at runtime and combined with:
- Task context (name, description, custom fields)
- Project information
- Swarm memory (swarm_memory.md)
- User preferences (user_preferences.md)

## Customization

Prompts can be customized per-project by:
1. Copying prompt to `.aegis/prompts/` in project root
2. Modifying as needed
3. System will prefer project-local prompts over global ones
