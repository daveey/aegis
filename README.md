# Aegis: Autonomous Software Development Swarm

Aegis is an intelligent agent orchestration system that turns Asana into a command center for autonomous software development. It uses a "swarm" of specialized LLM agents (powered by Claude Code) to plan, build, review, and merge code, all managed through a local Python orchestrator.

## 🚀 Key Features

- **Asana-First Interface**: Manage your AI workforce using standard Asana tasks and boards.
- **Multi-Agent Swarm**: Specialized agents for Triage, Planning, Coding, Reviewing, and Merging.
- **Safe Execution**:
  - **Git Worktrees**: Every task runs in an isolated environment.
  - **Safe Merge Protocol**: Code is verified in a staging area before merging to main.
  - **Human-in-the-Loop**: "Clarification Needed" states and manual approval gates.
- **Reliable Orchestration**: PID locking, zombie task recovery, and automatic dependency handling.

## 📚 Documentation

- **[New Architecture Summary](docs/architecture/NEW_ARCHITECTURE_SUMMARY.md)**: Technical overview of the v2.0 system.
- **[Design Document](docs/architecture/design.md)**: Deep dive into the system architecture and philosophy.
- **[Migration Plan](migration_plan.md)**: Guide for upgrading from v1.0.
- **[Project Structure](PROJECT_STRUCTURE.md)**: Layout of the codebase.
- **[LLM Architecture](docs/architecture/LLM_ARCHITECTURE.md)**: Guide for LLMs understanding this system.

## 🛠️ Quick Start

### Prerequisites

- Python 3.12+
- `uv` (for package management)
- Asana Account (Workspace + PAT)
- Anthropic API Key

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/yourusername/aegis.git
   cd aegis
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and Project GID
   ```

4. **Sync Asana Schema**:
   ```bash
   # Ensure your Asana project has the correct sections and fields
   python tools/sync_asana_project.py --project <YOUR_PROJECT_GID>
   ```

### Usage

Start the orchestrator:

```bash
aegis start
```

Now, go to your Asana project:
1. Create a task in **Drafts**.
2. Move it to **Ready Queue**.
3. Aegis will pick it up, assign it to the **Triage Agent**, and begin work.

## 🏗️ Architecture Overview

The system operates as a state machine driven by Asana sections:

`Drafts` → `Ready Queue` → `In Progress` → `Review` → `Merging` → `Done`

- **Orchestrator**: Polls Asana, manages git worktrees, and dispatches agents.
- **Agents**:
  - **Triage**: Analyzes requirements.
  - **Planner**: Designs the solution.
  - **Worker**: Writes the code.
  - **Reviewer**: Tests and reviews.
  - **Merger**: Safely integrates changes.

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT
