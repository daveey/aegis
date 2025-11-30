# Aegis Migration Plan

This guide outlines the steps to migrate an existing Aegis installation to the new Swarm Architecture (v2.0).

**Target Audience**: Developers and Users migrating to v2.0.

---

## 1. Update Codebase

Pull the latest changes from the repository.

```bash
git pull origin main
```

## 2. Install Dependencies

Aegis v2.0 uses `uv` for package management.

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies
uv sync
```

## 3. Asana Configuration

The new architecture relies on a specific set of Custom Fields and Project Sections.

### 3.1 Custom Fields

You must create the following Custom Fields in your Asana Workspace (or Portfolio) and add them to your Aegis project.

| Field Name | Type | Options |
|------------|------|---------|
| **Agent** | Single Select | Triage, Planner, Worker, Reviewer, Merger, Documentation |
| **Swarm Status** | Single Select | Idle, Running, Blocked, Complete |
| **Session ID** | Text | - |
| **Cost** | Number | - |
| **Max Cost** | Number | - |
| **Merge Approval** | Single Select | Auto-Approve, Manual Check, Approved |
| **Worktree Path** | Text | - |

### 3.2 Sync Project Sections

We have provided a tool to automatically sync your Asana project sections to the new canonical structure.

```bash
# 1. Find your Project GID (from Asana URL: app.asana.com/0/<PROJECT_GID>/...)
export ASANA_PROJECT_GID="<your_project_gid>"

# 2. Run a Dry Run to see what will happen
python tools/sync_asana_project.py --project $ASANA_PROJECT_GID --dry-run

# 3. Apply the changes
python tools/sync_asana_project.py --project $ASANA_PROJECT_GID
```

**Note**: Existing sections that do not match the new structure will be preserved but logged as "Unknown". You may manually move tasks from old sections to the new ones (e.g., "Drafts", "Ready Queue") after the sync.

## 4. Initialize Configuration

### 4.1 Environment Variables

Update your `.env` file with any new required variables.

```bash
# Check the example
cat .env.example

# Ensure you have:
ASANA_PAT="..."
ASANA_PROJECT_ID="..."
ANTHROPIC_API_KEY="..."
```

### 4.2 Memory Files

Ensure the following files exist in your project root. If not, create them or copy from templates.

- `swarm_memory.md`: Global project context.
- `user_preferences.md`: Your personal rules and preferences.

## 5. Start the Orchestrator

You are now ready to start the new Aegis Orchestrator.

```bash
# Start in foreground (recommended for first run)
aegis start

# Or start as a daemon
aegis start --daemon
```

---

## Code Migration Plan (For Developers)

If you are contributing to Aegis or have custom modifications, here is the plan for finalizing the v2.0 codebase.

### Deprecated Code Removal

The following files are part of the legacy v1.0 architecture and should be removed:

- `src/aegis/orchestrator/agent_client.py`
- `src/aegis/orchestrator/prioritizer.py`
- `src/aegis/agents/simple_executor.py`
- `src/aegis/agents/agent_service.py`
- `src/aegis/agents/formatters.py`
- `src/aegis/agents/prompts.py`
- `src/aegis/orchestrator/main.py` (Replaced by `dispatcher.py`)

### CLI Updates

The `src/aegis/cli.py` entry point needs to be updated to support the new architecture:

1.  **`aegis start`**: Must now initialize `SwarmDispatcher` instead of the old orchestrator.
2.  **`aegis create`**: Implement the new project bootstrapping logic.
3.  **`aegis init`**: Add command to generate default config files.
4.  **`aegis sync`**: Wrap `tools/sync_asana_project.py`.
5.  **Remove**: `work-on`, `organize`, `plan` commands.

### Custom Agent Migration

If you have written custom agents, you must refactor them to inherit from `BaseAgent` (`src/aegis/agents/base.py`).

**Key Changes**:
- **Inheritance**: `class MyAgent(BaseAgent):`
- **Method**: Implement `async def run(self, task: AsanaTask) -> AgentResult:`
- **Output**: Return `AgentResult` with `output` (summary) and `transitions` (next state).
- **Tools**: Use `self.console` for Claude Code interactions.
