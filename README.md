# Aegis

**Intelligent Assistant Orchestration System using Asana as the Control Plane**

Aegis is an autonomous agent swarm orchestration platform that uses Asana for task management and communication. Instead of building yet another chat interface, Aegis leverages Asana's familiar project management UI to coordinate complex, multi-step tasks through specialized AI agents.

## Quick Start

This project is currently in the design phase. To get started:

1. Review the project vision and architecture in [`design/PROJECT_OVERVIEW.md`](design/PROJECT_OVERVIEW.md)
2. Check the detailed task list and roadmap in [`design/TASK_LIST.md`](design/TASK_LIST.md)
3. Start with Phase 1 (Foundation/MVP) tasks

## Project Structure

```
aegis/
├── design/                 # Design documents and planning
│   ├── PROJECT_OVERVIEW.md # High-level project description
│   └── TASK_LIST.md        # Detailed task breakdown and roadmap
├── src/                    # Source code (coming soon)
├── tests/                  # Test suite (coming soon)
└── README.md              # This file
```

## Core Concept

Users interact with Aegis through Asana by:
- Creating tasks in designated Asana projects
- Assigning tasks to Aegis
- Providing requirements in task descriptions
- Receiving updates through comments and status changes
- Getting deliverables via attachments

Aegis orchestrates a swarm of specialized agents to:
- Parse and understand task requirements
- Decompose complex tasks into subtasks
- Execute work using Claude Code and other tools
- Coordinate multiple agents working in parallel
- Report progress and ask clarifying questions
- Deliver results back through Asana

## Key Features (Planned)

- **Asana-First Interface**: All interaction through Asana projects and tasks
- **Agent Swarm**: Multiple specialized agents (router, planner, executor, reviewer)
- **Intelligent Orchestration**: Automatic task decomposition and dependency management
- **Knowledge Management**: Vector database for context and memory
- **Multi-Modal**: Handle code, text, images, and documents
- **Autonomous**: Minimal human intervention after task assignment

## Development Phases

1. **Phase 1 - Foundation (MVP)**: Basic Asana integration + single agent execution
2. **Phase 2 - Orchestration**: Multi-agent coordination and task decomposition
3. **Phase 3 - Intelligence**: Advanced memory, learning, and context retrieval
4. **Phase 4 - Scale**: Production infrastructure and multi-tenancy

## Tech Stack

- **Language**: Python 3.11+
- **LLM**: Claude (Anthropic API / Claude Code)
- **Interface**: Asana API
- **Database**: PostgreSQL + Vector DB (Pinecone/Qdrant)
- **Cache**: Redis
- **Orchestration**: asyncio-based custom framework

## Current Status

🏗️ **In Design Phase** - Currently defining architecture and building roadmap

## Documentation

- [Project Overview](design/PROJECT_OVERVIEW.md) - Vision, architecture, and system design
- [Task List](design/TASK_LIST.md) - Detailed implementation roadmap

## Contributing

This is currently a personal project in early design stages. More information on contributing will be added as the project develops.

## License

TBD
