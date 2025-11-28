# Aegis Setup Guide

**Version**: 2.0 (New Swarm Architecture)
**Last Updated**: 2025-11-28

This guide will help you set up and run the new Aegis swarm system.

---

## Prerequisites

1. **Python 3.11+**
2. **uv** (Python package manager): `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. **Git** 2.5+ (for worktree support)
4. **PostgreSQL** (optional, for advanced features)
5. **Asana Account** with workspace access
6. **Anthropic API Key** (for Claude)

---

## Quick Start (5 minutes)

### 1. Clone and Install

```bash
cd /path/to/aegis
uv venv
source .venv/bin/activate
uv sync
```

### 2. Interactive Configuration ⭐ NEW!

```bash
aegis configure
```

This **interactive wizard** will:
- 🌐 Open browser tabs to help you get tokens
- ✅ Test your Asana connection automatically
- 📝 Auto-discover workspaces, teams, and portfolios
- 💾 Save everything to `.env` file
- ✨ Verify the configuration works

**OR** Manual Configuration:

```bash
cp .env.example .env
# Edit .env with your credentials
```

Required credentials:
- **Asana Personal Access Token**: Get from [Asana → Apps](https://app.asana.com/0/my-apps)
- **Anthropic API Key**: Get from [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)

### 3. Setup Asana Custom Fields

```bash
# Dry run first to see what will be created
python tools/setup_asana_custom_fields.py --dry-run

# Create the 7 required custom fields
python tools/setup_asana_custom_fields.py
```

This creates:
- Agent (enum): Triage, Planner, Worker, Reviewer, Merger, etc.
- Swarm Status (enum): Idle, Running, Blocked, Complete
- Session ID (text): UUID for execution tracking
- Cost (number): Accumulated cost in USD
- Max Cost (number): Cost limit (default: $2.00)
- Merge Approval (enum): Auto-Approve, Manual Check, Approved
- Worktree Path (text): Git worktree location

### 4. Setup Project Sections

```bash
# Sync one project
python tools/sync_asana_sections.py --project "Project Name"

# Or sync all projects in portfolio
python tools/sync_asana_sections.py --portfolio
```

This adds 8 canonical sections:
1. Drafts
2. Clarification Needed
3. Planning
4. Ready Queue
5. In Progress
6. Review
7. Merging
8. Done

### 5. Start the Swarm

```bash
aegis start "Project Name"
```

That's it! The swarm is now monitoring your project.

---

## How It Works

### Task Lifecycle

1. **Create Task** in "Drafts" section in Asana
2. **Move to Ready Queue** when ready for processing
3. **Triage Agent** analyzes requirements
   - If clear → Routes to Planner
   - If vague → Creates clarification questions
4. **Planner Agent** designs architecture
5. **Worker Agent** implements in isolated git worktree
6. **Reviewer Agent** tests and validates
7. **Merger Agent** safely integrates to main branch
8. **Task moves to Done**

### Agent Routing

| Section | Agent Field | What Happens |
|---------|-------------|--------------|
| Ready Queue | Triage | Analyzes and routes task |
| Planning | Planner | Designs implementation |
| Ready Queue | Worker | Implements code |
| Review | Reviewer | Tests and validates |
| Merging | Merger | Integrates to main |

### Git Worktrees

Each task gets an isolated environment:

```
_worktrees/
├── task-1234567890/          # Worker's isolated worktree
│   ├── .env -> ../../.env    # Symlinked
│   ├── src/                  # Code changes here
│   └── ...
└── merger_staging/           # Merger's isolated worktree
    └── ...                   # Always on main branch
```

**Benefits**:
- No cross-contamination between tasks
- Safe parallel execution
- Auto-cleanup on completion

---

## CLI Commands

### Core Operations

```bash
# Start swarm for a project
aegis start "Project Name"
aegis start 1212085431574340

# Stop running swarm
aegis stop

# Check status
aegis status
```

### Setup & Configuration

```bash
# Interactive configuration wizard ⭐ NEW!
aegis configure

# View current configuration
aegis config

# Test Asana connection
aegis test-asana

# Initialize configuration files
aegis init

# Create new project (planned)
aegis create "New Project Name"
```

### Management

```bash
# Sync project sections
aegis sync --project "Project Name"
aegis sync --portfolio              # Sync all projects

# View logs
aegis logs
```

---

## Configuration Files

### aegis_config.json

Main configuration (in repo root):

```json
{
  "hydration_command": "uv sync",
  "default_max_cost": 2.00,
  "poll_interval_seconds": 10,
  "watchdog_interval_seconds": 60,
  "silent_timeout_seconds": 300,
  "memory_file": "swarm_memory.md",
  "worktree_dir": "_worktrees",
  "pid_file": ".aegis.pid"
}
```

### swarm_memory.md

Global project context - updated by Documentation Agent:

```markdown
# Aegis Swarm Memory

## Architecture Decisions
- 2025-11-28: Adopted multi-agent architecture
- Using Asana as UI and state store

## Current State
- Infrastructure layer complete
- All core agents implemented
```

### user_preferences.md

User rules and preferences:

```markdown
# User Preferences

## Code Style
- Use `uv` for package management
- Type hints for all functions
- Google-style docstrings

## Testing
- Aim for 90%+ coverage
- Run tests before merging
```

### swarm_state.json

Persistent orchestrator state (auto-managed):

```json
{
  "orchestrator": {
    "started_at": "2025-11-28T...",
    "last_poll": "2025-11-28T...",
    "active_tasks": ["1234567890"]
  },
  "blocked_tasks": {},
  "custom_field_gids": {}
}
```

---

## Advanced Setup

### Database (Optional)

For full features, setup PostgreSQL:

```bash
# Install PostgreSQL
brew install postgresql@16

# Create database
createdb aegis

# Run migrations
alembic upgrade head
```

Update `.env`:

```bash
DATABASE_URL="postgresql://localhost/aegis"
```

### Custom Prompts

Customize agent behavior by editing prompts:

```bash
# Edit prompts
vim prompts/triage.md
vim prompts/planner.md
vim prompts/worker.md
# etc.
```

Changes take effect on next agent run.

### Cost Limits

Set per-task cost limits:

1. In Asana, set "Max Cost" field (default: $2.00)
2. Task execution stops when cost exceeded
3. Watchdog agent monitors spending (planned)

---

## Troubleshooting

### Issue: "PID lock already held"

**Cause**: Another dispatcher is running

**Solution**:
```bash
aegis stop
# Or manually: rm .aegis.pid
```

### Issue: "Zombie tasks found"

**Cause**: Dispatcher crashed with tasks in progress

**Solution**: Automatic! On next startup, orphaned tasks are moved back to Ready Queue

### Issue: "Worktree already exists"

**Cause**: Previous task crashed without cleanup

**Solution**: Automatic! Orphaned worktrees are pruned on startup

### Issue: "Tests failed after merge"

**Cause**: Merge conflict or integration issue

**Solution**: Task moved back to Review. Reviewer will investigate.

### Issue: "Custom field not found"

**Cause**: Custom fields not created in Asana

**Solution**:
```bash
python tools/setup_asana_custom_fields.py
```

---

## Best Practices

### Creating Tasks

**Good Task**:
```
Title: Add user authentication with JWT
Description: Implement JWT-based authentication:
- Login endpoint POST /auth/login
- Logout endpoint POST /auth/logout
- Middleware to verify tokens
- Use bcrypt for password hashing
```

**Bad Task**:
```
Title: Make app better
Description: (blank)
```

### Using Dependencies

Link tasks in Asana to create dependencies:

```
Task A: Design API schema
  └─> Task B: Implement API endpoints (blocks until A complete)
      └─> Task C: Add API tests (blocks until B complete)
```

### Preferences

Record rules for the swarm:

```
Title: Preference: Always use async/await for DB operations
Description: All database operations must use async/await pattern
for consistency and performance.
```

### Cost Management

Monitor costs in Asana "Cost" field:

```
Task 1: $0.15 (Triage)
Task 2: $1.85 (Planner + Worker + Reviewer)
```

Adjust "Max Cost" if needed.

---

## Architecture Overview

### Components

```
┌─────────────┐
│    Asana    │  (UI & State Store)
└──────┬──────┘
       │
┌──────▼──────────────────────────────┐
│      SwarmDispatcher                │
│  - Polls Asana sections             │
│  - Routes tasks to agents           │
│  - Manages worktrees                │
└──────┬──────────────────────────────┘
       │
       ├─> TriageAgent     (Requirements)
       ├─> PlannerAgent    (Architecture)
       ├─> WorkerAgent     (Implementation)
       ├─> ReviewerAgent   (QA)
       ├─> MergerAgent     (Integration)
       └─> DocumentationAgent (Knowledge)
```

### State Machine

```
Drafts → Ready Queue → Planning → Ready Queue → In Progress
                         ↓           ↓             ↓
                    (Planner)    (Worker)      (active)
                                                   ↓
              Clarification ← ← ← ← ← ← ← ← ← Review
               Needed                             ↓
                                              Merging
                                                   ↓
                                                Done
```

---

## Next Steps

1. **Read Documentation**:
   - `NEW_ARCHITECTURE_SUMMARY.md` - Technical overview
   - `design.md` - Complete design specification
   - `prompts/` - Agent prompt templates

2. **Try It Out**:
   - Create a simple task in Asana
   - Move to Ready Queue
   - Watch the swarm work!

3. **Customize**:
   - Edit prompts for your project
   - Add preferences via Documentation tasks
   - Tune cost limits

4. **Monitor**:
   - Check `logs/aegis.log`
   - View task comments in Asana
   - Use `aegis status`

---

## Getting Help

- **Issue**: Check troubleshooting section above
- **Bug**: Review logs in `logs/aegis.log`
- **Question**: Read `CLAUDE.md` for development guide
- **Feature Request**: Create task in Asana!

---

## Summary

You now have:
- ✅ Aegis installed and configured
- ✅ Asana custom fields created
- ✅ Project sections synchronized
- ✅ Swarm dispatcher running

**What happens next**:
1. Create tasks in Asana "Drafts"
2. Move to "Ready Queue" when ready
3. Swarm picks up and processes automatically
4. Code appears in main branch when complete

**Happy swarming! 🐝**

---

**Last Updated**: 2025-11-28
**Version**: 2.0
