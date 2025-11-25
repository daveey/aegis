# Aegis Operator Guide

**Version:** 0.1.0
**Status:** Alpha

This guide provides comprehensive instructions for installing, configuring, running, and operating the Aegis orchestration system.

---

## Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Configuration](#configuration)
5. [Database Setup](#database-setup)
6. [Running Aegis](#running-aegis)
7. [Monitoring and Logs](#monitoring-and-logs)
8. [Troubleshooting](#troubleshooting)
9. [Maintenance](#maintenance)

---

## Overview

Aegis is an intelligent assistant orchestration system that uses Asana as a control plane for managing and executing tasks through AI agents. The system:

- Monitors Asana portfolios for new tasks
- Executes tasks using Claude CLI in the appropriate project context
- Reports progress and results back to Asana
- Maintains execution logs and state

**Architecture:**
- **Language:** Python 3.11+
- **Task Management:** Asana API
- **AI Execution:** Claude (via Claude CLI)
- **Database:** PostgreSQL (optional, for state management)
- **Cache:** Redis (optional, for performance)
- **Vector DB:** Qdrant (optional, for advanced features)

### Quick Start Checklist

Get up and running in 5 steps:

1. **Install Prerequisites**
   - [ ] Python 3.11+ installed
   - [ ] Claude CLI installed: `npm install -g @anthropic-ai/claude-cli`
   - [ ] Get Asana Personal Access Token
   - [ ] Get Anthropic API Key

2. **Install Aegis**
   ```bash
   git clone <repo-url> && cd aegis
   python3 -m venv .venv && source .venv/bin/activate
   pip install -e .
   ```

3. **Configure**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   aegis config  # Verify
   ```

4. **Test Connections**
   ```bash
   aegis test-asana   # Test Asana API
   aegis test-claude  # Test Claude API
   ```

5. **Run Your First Task**
   ```bash
   aegis do <project_name>
   # Or for autonomous multi-task execution:
   aegis work-on <project_name>
   ```

Continue reading for detailed installation and configuration instructions.

---

## Prerequisites

### Required

1. **Python 3.11 or higher**
   ```bash
   python3 --version  # Should be 3.11+
   ```

2. **Claude CLI**
   ```bash
   npm install -g @anthropic-ai/claude-cli
   claude --version
   ```

3. **Asana Account**
   - Personal Access Token with read/write permissions
   - A workspace with at least one portfolio
   - Projects in the portfolio representing work to be orchestrated

4. **Anthropic API Key**
   - Account at https://console.anthropic.com
   - API key with sufficient credits

### Optional

5. **PostgreSQL** (for persistent state management)
   ```bash
   # macOS
   brew install postgresql@16

   # Ubuntu/Debian
   sudo apt-get install postgresql-16
   ```

6. **Redis** (for caching and performance)
   ```bash
   # macOS
   brew install redis

   # Ubuntu/Debian
   sudo apt-get install redis-server
   ```

7. **Qdrant** (for vector database features)
   ```bash
   docker run -p 6333:6333 qdrant/qdrant
   ```

---

## Installation

### 1. Clone the Repository

```bash
git clone <repository-url>
cd aegis
```

### 2. Create Virtual Environment

Using `venv`:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

Or using `uv` (recommended for faster installs):
```bash
uv venv
source .venv/bin/activate
```

### 3. Install Dependencies

Using `pip`:
```bash
pip install -e .
```

Or using `uv`:
```bash
uv pip install -e .
```

For development dependencies:
```bash
pip install -e ".[dev]"
# or
uv pip install -e ".[dev]"
```

### 4. Verify Installation

```bash
aegis --version
# Should output: aegis, version 0.1.0
```

---

## Configuration

### 1. Create Configuration File

Copy the example environment file:
```bash
cp .env.example .env
```

### 2. Get Asana Credentials

#### Get Personal Access Token:
1. Log in to Asana
2. Go to **Settings** → **Apps** → **Developer apps**
3. Click **Create new personal access token**
4. Copy the token (you won't be able to see it again)

#### Get Workspace GID:
```bash
# Using browser: Navigate to your workspace and copy GID from URL
# https://app.asana.com/0/<WORKSPACE_GID>/list
```

Or use the Asana API explorer at https://developers.asana.com/reference/getworkspaces

#### Get Portfolio GID:
1. Create a portfolio in Asana (or use existing one)
2. Navigate to the portfolio
3. Copy the GID from the URL: `https://app.asana.com/0/portfolio/<PORTFOLIO_GID>`

### 3. Configure Environment Variables

Edit `.env` with your credentials:

```bash
# Asana Configuration (REQUIRED)
ASANA_ACCESS_TOKEN=your_asana_personal_access_token_here
ASANA_WORKSPACE_GID=your_workspace_gid
ASANA_PORTFOLIO_GID=your_portfolio_gid

# Anthropic Configuration (REQUIRED)
ANTHROPIC_API_KEY=your_anthropic_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
ANTHROPIC_MAX_TOKENS=4096

# Database Configuration (OPTIONAL)
DATABASE_URL=postgresql://localhost/aegis
REDIS_URL=redis://localhost:6379

# Vector Database Configuration (OPTIONAL)
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=
QDRANT_COLLECTION=aegis

# Orchestrator Configuration
POLL_INTERVAL_SECONDS=30
MAX_CONCURRENT_TASKS=5

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=json

# Feature Flags
ENABLE_VECTOR_DB=false
ENABLE_MULTI_AGENT=false
```

### 4. Verify Configuration

```bash
aegis config
```

This will display your current configuration (with sensitive values masked).

---

## Database Setup

You can set up databases either manually or using Docker Compose.

### Option 1: Docker Compose (Recommended)

Easiest way to run all optional services:

#### 1. Create docker-compose.yml

The project includes a ready-to-use `docker-compose.yml` file:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    container_name: aegis-postgres
    environment:
      POSTGRES_USER: aegis
      POSTGRES_PASSWORD: aegis_dev_password
      POSTGRES_DB: aegis
    ports:
      - "5432:5432"
    volumes:
      - aegis_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U aegis -d aegis"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: aegis-redis
    ports:
      - "6379:6379"
    volumes:
      - aegis_redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  aegis_postgres_data:
  aegis_redis_data:
```

#### 2. Start Services

```bash
# Start all services
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

#### 3. Run Migrations

```bash
# Initialize database schema
alembic upgrade head
```

#### 4. Update .env

Update your `.env` file to use the Docker Compose credentials:

```bash
DATABASE_URL=postgresql://aegis:aegis_dev_password@localhost:5432/aegis
REDIS_URL=redis://localhost:6379
```

**Note:** The docker-compose.yml file does not include Qdrant by default. If you need vector database features, you can add a Qdrant service or run it separately.

#### 5. Stop Services

```bash
# Stop but keep data
docker compose stop

# Stop and remove (keeps volumes)
docker compose down

# Remove everything including data
docker compose down -v
```

### Option 2: Manual Setup

#### PostgreSQL Setup (Optional)

If you want persistent state management:

**1. Create Database**

```bash
# Create the database
createdb aegis

# Or using psql
psql -c "CREATE DATABASE aegis;"
```

**2. Run Migrations**

```bash
# Initialize alembic (if not already done)
alembic upgrade head
```

**3. Verify Database**

```bash
psql aegis -c "\dt"
# Should show tables: tasks, agents, executions, etc.
```

#### Redis Setup (Optional)

If you want caching:

```bash
# macOS
brew services start redis

# Ubuntu/Debian
sudo systemctl start redis-server

# Verify connection
redis-cli ping
# Should return: PONG
```

#### Qdrant Setup (Optional)

If you want vector database features:

```bash
# Start Qdrant via Docker
docker run -d -p 6333:6333 qdrant/qdrant

# Verify connection
curl http://localhost:6333/collections
```

---

## Running Aegis

### CLI Command Reference

Aegis provides several commands for managing and executing tasks:

```bash
aegis --version              # Show version
aegis --help                 # Show help
aegis config                 # Display configuration
aegis test-asana            # Test Asana API connection
aegis test-claude           # Test Claude API connection
aegis do <project>          # Execute first task from project
aegis work-on <project>     # Autonomous multi-task execution
aegis start                 # Start orchestrator (coming soon)
```

**Quick Reference:**

| Command | Purpose | Use Case | Status |
|---------|---------|----------|--------|
| `config` | View settings | Verify configuration before running | ✅ Ready |
| `test-asana` | Test Asana connection | Validate credentials and portfolio | ✅ Ready |
| `test-claude` | Test Claude API | Validate Anthropic API access | ⚠️ Not yet implemented |
| `do` | Execute one task | Quick single-task execution | ✅ Ready |
| `work-on` | Execute multiple tasks | Autonomous project progression | ✅ Ready |
| `start` | Run orchestrator loop | Continuous monitoring | ⚠️ Not yet implemented |

See [TOOLS.md](../TOOLS.md) for detailed command documentation.

### Test Connections

Before running the orchestrator, verify your configuration:

#### Test Asana Connection

```bash
aegis test-asana
```

This will:
- Connect to Asana using your credentials
- Fetch the specified portfolio
- List all projects in the portfolio
- Verify API access

**Expected Output:**
```
Testing Asana connection to portfolio: 1234567890...

Fetching portfolio details...
✓ Portfolio: Aegis Projects

Fetching projects in portfolio...
✓ Found 3 projects

First 5 projects:
  - Aegis (GID: 1234567890)
  - Example Project (GID: 0987654321)
  - Another Project (GID: 1122334455)

Asana API connection successful!
```

#### Test Claude API Connection

```bash
aegis test-claude
```

**Current Status:** This command is not yet fully implemented. You will see:
```
Testing Claude API connection...
Note: Claude client not yet implemented
```

For now, you can verify Claude API access by:
1. Running `aegis do <project>` on a test task
2. Or testing the Claude CLI directly: `echo "Hello" | claude`

### Execute a Single Task

To execute the first incomplete task from a specific project:

```bash
aegis do <project_name>
```

**Example:**
```bash
aegis do Aegis
```

**What happens:**
1. Finds the project "Aegis" in your portfolio
2. Retrieves the first incomplete task
3. Extracts code location from project notes
4. Executes the task using Claude CLI
5. Logs output to `logs/<project_name>.log`
6. Posts results back to Asana as a comment

**Output:**
```
Finding project 'Aegis'...
✓ Found project: Aegis (GID: 1234567890)

Fetching tasks...
✓ First incomplete task: Write operator documentation

Task URL: https://app.asana.com/0/1234567890/9876543210

Executing task with Claude CLI...

Task: Write operator documentation
Working directory: /Users/daveey/code/aegis
Logging to: logs/aegis.log

============================================================

[Claude CLI output appears here...]

============================================================

Posting results to Asana...
✓ Comment posted to Asana

✓ Task execution completed
```

### Autonomous Work on a Project

For more intelligent, autonomous execution that handles dependencies and blockers:

```bash
aegis work-on <project_name> [--max-tasks N] [--dry-run]
```

**Example:**
```bash
# Work autonomously on Aegis project
aegis work-on Aegis

# Limit to 3 tasks in this session
aegis work-on Aegis --max-tasks 3

# Preview what would be done without executing
aegis work-on Aegis --dry-run
```

**What happens:**
1. Fetches all incomplete unassigned tasks from the project
2. Analyzes task descriptions for dependencies and blockers
3. Checks environment prerequisites (PostgreSQL, Redis, etc.)
4. Creates question tasks for blockers (assigned to portfolio owner)
5. Identifies ready tasks with no blockers
6. Executes multiple ready tasks (up to `--max-tasks` limit)
7. Reports comprehensive session summary

**Key Features:**
- **Dependency Detection**: Parses task descriptions for "Dependencies:", "Depends on:", "Blocked by:"
- **Environment Checks**: Verifies required services are running
- **Intelligent Question Creation**: Auto-creates tasks with multiple options when blocked
- **Multi-Task Execution**: Processes multiple ready tasks in one session
- **Smart Task Selection**: Only executes tasks with no blockers

**Output:**
```
Analyzing Aegis project...
✓ Found 17 incomplete unassigned tasks

Assessing project state...
⚠ Blocked tasks: 5
  • Set up PostgreSQL database
    Reason: Requires PostgreSQL (container not running)
  • Configure Alembic migrations
    Reason: Has explicit dependencies in description

? Questions to create: 1
  • PostgreSQL Setup

✓ Ready tasks: 12
  • Design base Agent class
  • Implement Anthropic API client wrapper
  • Create prompt templates for SimpleExecutor
  • Build SimpleExecutor agent
  • Implement task response formatter

Creating question tasks...
  ✓ Created: Question: PostgreSQL Setup (GID: 1234567890)

Executing 5 ready task(s)...

[1/5] Design base Agent class
  Working directory: /Users/daveey/code/aegis
  ✓ Completed

[2/5] Implement Anthropic API client wrapper
  Working directory: /Users/daveey/code/aegis
  ✓ Completed

...

============================================================
Session Summary
  ✓ Completed: 5 tasks
  ⚠ Blocked: 5 tasks
  ? Questions: 1 created

Log: /Users/daveey/code/aegis/logs/aegis.log
============================================================
```

**When to Use:**

| Use `aegis do` | Use `aegis work-on` |
|----------------|---------------------|
| Single task execution | Autonomous multi-task execution |
| No dependency checking | Full dependency analysis |
| Quick, simple execution | Strategic project progression |
| Manual task selection | Intelligent task selection |
| No question creation | Auto-creates questions for blockers |

See [TOOLS.md](../TOOLS.md) for detailed command comparison and design documentation.

### Start the Orchestrator (Coming Soon)

```bash
aegis start
```

**Note:** The full orchestration loop is not yet implemented. Currently, use `aegis do <project>` for manual task execution.

---

## Monitoring and Logs

### Log Files

Aegis creates log files for each project execution:

```bash
logs/
├── aegis.log          # Logs for "Aegis" project
├── example.log        # Logs for "Example Project"
└── another.log        # Logs for "Another Project"
```

**Log Format:**
```
================================================================================
[2025-11-25T10:30:00] Task: Write operator documentation
================================================================================

[Claude CLI output...]

Exit code: 0
```

### View Logs

```bash
# View latest log
tail -f logs/<project_name>.log

# View all logs
cat logs/<project_name>.log

# Search logs for errors
grep -i error logs/<project_name>.log
```

### Asana Updates

All task executions post results to Asana as comments:

**Comment Format:**
```
✓ Task completed via Aegis

**Timestamp**: 2025-11-25T10:30:00

**Output**:
```
[Task output...]
```

**Log file**: `logs/aegis.log`
```

### Monitoring Checklist

**Before Each Run:**
- [ ] Check configuration: `aegis config`
- [ ] Test Asana connection: `aegis test-asana`
- [ ] Verify Claude CLI works: `claude --version`
- [ ] Check disk space for logs: `df -h .`
- [ ] Verify working directory exists: Check project notes in Asana

**During Execution:**
- [ ] Monitor console output for errors
- [ ] Watch log files: `tail -f logs/*.log`
- [ ] Check Asana for task updates and comments
- [ ] Monitor API credit usage at console.anthropic.com
- [ ] Watch for network connectivity issues

**After Execution:**
- [ ] Review exit codes in logs
- [ ] Check Asana comments for completion status
- [ ] Verify task outputs/deliverables in working directory
- [ ] Check for any partial completions or errors
- [ ] Review log file size: `ls -lh logs/`

**Weekly Maintenance:**
- [ ] Archive old logs (see Maintenance section)
- [ ] Review API usage and costs
- [ ] Check for Aegis updates: `git pull && pip install -U -e .`

---

## Troubleshooting

### Common Issues

#### 1. "Error loading configuration"

**Symptom:**
```
Error loading configuration: Field required [type=missing, input_value={...}]
```

**Cause:** Missing required environment variables in `.env`

**Solution:**
```bash
# Check which variables are set
aegis config

# Ensure all required variables are in .env:
# - ASANA_ACCESS_TOKEN
# - ASANA_WORKSPACE_GID
# - ASANA_PORTFOLIO_GID
# - ANTHROPIC_API_KEY
```

#### 2. "Project not found in portfolio"

**Symptom:**
```
Error: Project 'MyProject' not found in portfolio

Available projects:
  - Aegis
  - Example
```

**Cause:** Project name doesn't match or project not in portfolio

**Solution:**
```bash
# List projects in portfolio
aegis test-asana

# Use exact project name (case-insensitive)
aegis do Aegis

# Or add project to portfolio in Asana
```

#### 3. "Claude CLI not found"

**Symptom:**
```
Error: 'claude' CLI not found. Please install it first.
Install: npm install -g @anthropic-ai/claude-cli
```

**Cause:** Claude CLI not installed or not in PATH

**Solution:**
```bash
# Install Claude CLI
npm install -g @anthropic-ai/claude-cli

# Verify installation
claude --version

# Check PATH
which claude
```

#### 4. "Asana API connection failed"

**Symptom:**
```
Error testing Asana connection: 401 Unauthorized
```

**Cause:** Invalid or expired Asana access token

**Solution:**
```bash
# Regenerate token in Asana:
# Settings → Apps → Developer apps → Create new token

# Update .env
ASANA_ACCESS_TOKEN=your_new_token_here

# Test connection
aegis test-asana
```

#### 5. "Database connection error"

**Symptom:**
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Cause:** PostgreSQL not running or wrong connection URL

**Solution:**
```bash
# Start PostgreSQL
# macOS:
brew services start postgresql@16

# Ubuntu:
sudo systemctl start postgresql

# Verify database exists
psql -l | grep aegis

# Create if missing
createdb aegis

# Update .env if needed
DATABASE_URL=postgresql://localhost/aegis
```

#### 6. "Task completed with errors"

**Symptom:**
```
⚠️ Task completed with errors (exit code 1)
```

**Cause:** Claude CLI execution failed

**Solution:**
```bash
# Check log file for details
cat logs/<project>.log

# Common causes:
# - Insufficient API credits
# - Invalid task description
# - Missing project files
# - Permission issues

# Verify Anthropic API key
echo $ANTHROPIC_API_KEY

# Check API credits at console.anthropic.com
```

#### 7. "No ready tasks found" (aegis work-on)

**Symptom:**
```
⚠ Blocked tasks: 15
✓ Ready tasks: 0

No ready tasks to execute.
```

**Cause:** All tasks have blockers or dependencies

**Solution:**
```bash
# Run in dry-run mode to see what's blocked
aegis work-on <project> --dry-run

# Check for questions created in Asana
# Answer questions to unblock tasks

# Common blockers:
# - Missing PostgreSQL/Redis/Docker
# - Explicit dependencies in task descriptions
# - Environment prerequisites

# Start required services
brew services start postgresql@16
brew services start redis

# Or use Docker
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:16
```

#### 8. "Too many tasks in session" (aegis work-on)

**Symptom:**
```
Executing 15 ready task(s)...
```

**Cause:** Default max-tasks is 5, but more tasks are ready

**Solution:**
```bash
# Limit tasks per session
aegis work-on <project> --max-tasks 3

# Or increase the limit
aegis work-on <project> --max-tasks 10

# Run multiple sessions for large batches
for i in {1..3}; do
  aegis work-on <project> --max-tasks 5
done
```

#### 9. "Question task already exists"

**Symptom:**
```
⚠ Question already exists for this blocker
```

**Cause:** work-on detected same blocker in previous run

**Solution:**
```bash
# Answer the existing question in Asana
# Check project for tasks starting with "Question:"

# Or delete duplicate questions manually

# Re-run work-on after answering
aegis work-on <project>
```

#### 10. "Docker not found" (aegis work-on)

**Symptom:**
```
Error: 'docker' command not found
```

**Cause:** Docker CLI not installed or not in PATH (work-on uses docker to check service status)

**Solution:**
```bash
# Install Docker Desktop from https://docker.com

# Or ignore - this just prevents environment checks
# Tasks will still run, but blocker detection may miss some issues
```

#### 11. "Connection timeout" when posting to Asana

**Symptom:**
```
⚠ Failed to post comment: Connection timeout
```

**Cause:** Network issues or Asana API rate limiting

**Solution:**
- The command has built-in retry logic (3 attempts with exponential backoff)
- Task execution still completes successfully
- Comment will be in log file even if Asana post fails
- Check network connection
- Check Asana API status at https://status.asana.com
- Rate limit: 1500 requests/minute per token (rarely hit in normal use)

#### 12. "Invalid code location path"

**Symptom:**
Task executes in wrong directory or current directory instead of project directory

**Cause:** Code Location in Asana project notes is missing or incorrect

**Solution:**
```bash
# In Asana, edit project description (notes) to include:
Code Location: /absolute/path/to/your/project

# Example:
Code Location: /Users/username/code/myproject

# The path must:
# - Be absolute (not relative)
# - Exist on your filesystem
# - Be readable/writable by the user running aegis
```

#### 13. "Alembic migrations fail"

**Symptom:**
```
alembic.util.exc.CommandError: Can't locate revision identified by 'head'
```

**Cause:** Database schema not initialized or alembic directory missing

**Solution:**
```bash
# Check if alembic directory exists
ls alembic/

# If missing, initialize alembic
alembic init alembic

# If exists, check for migrations
ls alembic/versions/

# If no migrations exist yet, that's normal for fresh install
# Database features are optional
```

### Debug Mode

Enable detailed logging:

```bash
# Set in .env
LOG_LEVEL=DEBUG
LOG_FORMAT=console

# Run command
aegis do <project>
```

### Getting Help

1. **Check logs:** `logs/<project>.log`
2. **Review configuration:** `aegis config`
3. **Test connections:** `aegis test-asana`
4. **Check GitHub issues:** [Link to issues]
5. **Community support:** [Link to discussions]

---

## Maintenance

### Regular Tasks

#### Daily
- [ ] Review execution logs for errors
- [ ] Monitor Asana for stuck tasks
- [ ] Check API credit usage

#### Weekly
- [ ] Rotate/archive old logs
- [ ] Review completed tasks
- [ ] Update project configurations

#### Monthly
- [ ] Update dependencies: `pip install -U -e .`
- [ ] Backup database (if using PostgreSQL)
- [ ] Review and update documentation

### Backup and Recovery

#### Backup Configuration
```bash
# Backup .env file (exclude from git)
cp .env .env.backup

# Backup logs
tar -czf logs-backup-$(date +%Y%m%d).tar.gz logs/
```

#### Backup Database
```bash
# PostgreSQL backup
pg_dump aegis > aegis-backup-$(date +%Y%m%d).sql

# Restore
psql aegis < aegis-backup-20251125.sql
```

### Updates

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install -U -e .

# Run migrations (if any)
alembic upgrade head

# Restart services
aegis start
```

### Cleanup

```bash
# Remove old logs (older than 30 days)
find logs/ -name "*.log" -mtime +30 -delete

# Clear cache (if using Redis)
redis-cli FLUSHDB

# Clean Python cache
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

---

## Advanced Configuration

### Project Setup in Asana

For `aegis do` to work correctly, each project should have:

**Project Notes Format:**
```
Code Location: /path/to/project/code

[Other project description...]
```

The code location tells Aegis where to execute Claude CLI for that project's tasks.

**Example:**
```
Code Location: /Users/daveey/code/aegis

This project contains tasks for developing and maintaining the Aegis orchestration system.
```

### Multiple Portfolios

To monitor multiple portfolios, you can:

1. Run multiple instances with different `.env` files
2. Or modify the code to support multiple portfolios (future feature)

### Custom Claude Models

To use different Claude models:

```bash
# In .env
ANTHROPIC_MODEL=claude-opus-4-5-20251101
ANTHROPIC_MAX_TOKENS=8192
```

Available models:
- `claude-opus-4-5-20251101` (most capable)
- `claude-sonnet-4-5-20250929` (balanced performance and cost, default)
- `claude-haiku-3-5-20241022` (fastest, most economical)

---

## Security Best Practices

1. **Never commit `.env` to git**
   ```bash
   # .gitignore should include:
   .env
   .env.local
   ```

2. **Rotate tokens regularly**
   - Regenerate Asana tokens quarterly
   - Rotate Anthropic API keys as needed

3. **Limit token scope**
   - Use workspace-specific Asana tokens
   - Restrict API permissions to minimum required

4. **Secure database**
   ```bash
   # Use strong passwords
   DATABASE_URL=postgresql://user:strong_password@localhost/aegis

   # Enable SSL for remote databases
   DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
   ```

5. **Monitor API usage**
   - Track Anthropic API costs
   - Set up billing alerts
   - Monitor rate limits

---

## Performance Tuning

### Concurrent Tasks

```bash
# Increase for better throughput (default: 5)
MAX_CONCURRENT_TASKS=10

# Decrease to reduce load
MAX_CONCURRENT_TASKS=3
```

### Poll Interval

```bash
# More frequent polling (default: 30)
POLL_INTERVAL_SECONDS=15

# Less frequent (reduce API calls)
POLL_INTERVAL_SECONDS=60
```

### Token Limits

```bash
# Increase for complex tasks
ANTHROPIC_MAX_TOKENS=8192

# Decrease for cost savings
ANTHROPIC_MAX_TOKENS=2048
```

---

## Architecture Reference

```
┌─────────────────────────────────────────────────────────────┐
│                         Asana                               │
│  (Portfolio → Projects → Tasks)                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ API Calls
                         │
                    ┌────▼─────┐
                    │  Aegis   │
                    │  CLI     │
                    └────┬─────┘
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     ┌────▼────┐   ┌─────▼────┐   ┌────▼────┐
     │ Config  │   │ Database │   │  Logs   │
     │ (.env)  │   │   (PG)   │   │ (files) │
     └─────────┘   └──────────┘   └─────────┘
                         │
                         │ Executes
                         │
                    ┌────▼──────┐
                    │  Claude   │
                    │   CLI     │
                    └───────────┘
```

---

## Operational Tips

### Best Practices for Running Aegis

1. **Start Small**
   - Begin with simple tasks to verify your setup
   - Use `aegis do` for first few tasks before trying `aegis work-on`
   - Test with a single project before scaling to multiple

2. **Task Organization in Asana**
   - Keep task descriptions clear and specific
   - Include any relevant context, requirements, or constraints
   - Use Asana's task dependencies feature to show relationships
   - Add "Dependencies:" section in task notes for explicit blocking

3. **Monitoring Execution**
   - Always check the log files after execution
   - Review Asana comments to verify results were posted
   - Keep logs directory under version control exclusion (`.gitignore`)
   - Set up log rotation if running frequently

4. **Managing API Costs**
   - Default model (Sonnet) balances cost and performance
   - Monitor usage at console.anthropic.com
   - Use `--max-tasks` flag to limit work-on sessions
   - Consider using `--dry-run` first to preview what will execute

5. **Handling Errors**
   - Don't panic if a task fails - check logs for details
   - Asana comments capture output even on failures
   - Failed tasks remain incomplete and can be retried
   - Use `aegis work-on --dry-run` to diagnose blockers

6. **Working with Multiple Projects**
   - Create separate portfolios for different environments (dev/staging/prod)
   - Use consistent "Code Location:" format across projects
   - Consider using different .env files for different contexts
   - Run one project at a time to avoid conflicts

7. **Development Workflow**
   - Keep your working directories clean (git status before/after)
   - Review Claude's changes before committing
   - Use meaningful task names in Asana that describe the outcome
   - Break large features into smaller, atomic tasks

### Common Patterns

**Pattern: Progressive Task Refinement**
1. Create high-level task in Asana
2. Run `aegis do <project>` to get initial implementation
3. Review output and create follow-up tasks for improvements
4. Iterate until complete

**Pattern: Blocked Task Management**
1. Run `aegis work-on <project> --dry-run` to see blockers
2. Answer any questions created in Asana
3. Resolve blockers (start services, complete dependencies)
4. Run `aegis work-on <project>` to execute ready tasks
5. Repeat until project complete

**Pattern: Batch Processing**
```bash
# Process multiple projects in sequence
for project in ProjectA ProjectB ProjectC; do
  echo "Working on $project..."
  aegis work-on "$project" --max-tasks 3
  sleep 10  # Brief pause between projects
done
```

**Pattern: Continuous Monitoring** (Future)
```bash
# Not yet implemented, but planned:
aegis start  # Will continuously monitor portfolio and execute tasks
```

---

## FAQ

**Q: Can I run multiple Aegis instances simultaneously?**
A: Yes, but ensure each uses a different portfolio to avoid conflicts.

**Q: How do I prioritize certain projects?**
A: Use Asana's built-in project prioritization. Aegis respects task order.

**Q: Can I run Aegis without PostgreSQL?**
A: Yes, the database is optional. Basic functionality works without it.

**Q: What happens if Claude CLI fails?**
A: Aegis logs the error, posts to Asana, and continues with next tasks.

**Q: How do I upgrade Aegis?**
A: Run `git pull && pip install -U -e . && alembic upgrade head`

**Q: Can I use Aegis with other LLMs?**
A: Currently only Claude is supported. Other LLMs may be added in future.

---

## Support

- **Documentation:** `/docs` directory
- **Issues:** [GitHub Issues]
- **Discussions:** [GitHub Discussions]
- **Email:** [Support email]

---

## License

[License information]

---

**Last Updated:** 2025-11-25
**Document Version:** 1.2
**Aegis Version:** 0.1.0

## Changelog

### Version 1.2 (2025-11-25)
- Fixed Docker Compose configuration to match actual docker-compose.yml
  - Updated PostgreSQL credentials (aegis/aegis_dev_password)
  - Removed Qdrant from default compose (not in actual file)
  - Added container names and healthchecks documentation
- Updated default model to claude-sonnet-4-5-20250929 (matches .env.example)
- Clarified test-claude command status (not yet implemented)
- Added Status column to CLI command reference table
- Added 4 new troubleshooting scenarios (#10-13):
  - Docker not found error handling
  - Connection timeout and retry logic
  - Invalid code location path issues
  - Alembic migration problems
- Enhanced monitoring checklist with practical checks
- Added comprehensive Operational Tips section:
  - 7 best practices for running Aegis
  - 4 common workflow patterns
  - Batch processing example
- Fixed database URL examples to match actual compose setup

### Version 1.1 (2025-11-25)
- Added documentation for `aegis work-on` command
- Added documentation for `aegis test-claude` command
- Updated Claude model references to latest versions
- Added Docker Compose setup option for databases
- Added troubleshooting for `work-on` command scenarios
- Added CLI command reference table
- Added Quick Start Checklist
- Enhanced monitoring checklist with test-claude step

### Version 1.0 (2025-11-25)
- Initial comprehensive operator guide
