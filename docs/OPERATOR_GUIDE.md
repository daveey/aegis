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

### PostgreSQL Setup (Optional)

If you want persistent state management:

#### 1. Create Database

```bash
# Create the database
createdb aegis

# Or using psql
psql -c "CREATE DATABASE aegis;"
```

#### 2. Run Migrations

```bash
# Initialize alembic (if not already done)
alembic upgrade head
```

#### 3. Verify Database

```bash
psql aegis -c "\dt"
# Should show tables: tasks, agents, executions, etc.
```

### Redis Setup (Optional)

If you want caching:

```bash
# Start Redis
redis-server

# Verify connection
redis-cli ping
# Should return: PONG
```

### Qdrant Setup (Optional)

If you want vector database features:

```bash
# Start Qdrant via Docker
docker run -d -p 6333:6333 qdrant/qdrant

# Verify connection
curl http://localhost:6333/collections
```

---

## Running Aegis

### Test Asana Connection

Before running the orchestrator, verify your Asana configuration:

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

**During Execution:**
- [ ] Monitor console output for errors
- [ ] Watch log files: `tail -f logs/*.log`
- [ ] Check Asana for task updates

**After Execution:**
- [ ] Review exit codes in logs
- [ ] Check Asana comments for completion status
- [ ] Verify task outputs/deliverables

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
ANTHROPIC_MODEL=claude-opus-4-20250514
ANTHROPIC_MAX_TOKENS=8192
```

Available models:
- `claude-sonnet-4-5-20250929` (default, balanced)
- `claude-opus-4-20250514` (most capable)
- `claude-haiku-3-5-20241022` (fastest, economical)

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
**Document Version:** 1.0
**Aegis Version:** 0.1.0
