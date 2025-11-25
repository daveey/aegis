# Aegis Database Schema Design

## Overview

The Aegis database tracks all state related to task execution, agent activity, portfolio/project management, and system operations. It provides persistence, history, and enables analysis of agent performance over time.

## Database Technology

**PostgreSQL** - Selected for:
- Rich data types (JSONB for flexible metadata)
- Strong ACID guarantees for reliable state tracking
- Good Python ecosystem support (SQLAlchemy, psycopg2)
- Vector extension support (pgvector) for future semantic search

## Core Tables

### 1. Projects

Tracks Asana projects that Aegis monitors.

```sql
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    asana_gid VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    code_path TEXT,
    portfolio_gid VARCHAR(50) NOT NULL,
    workspace_gid VARCHAR(50) NOT NULL,
    team_gid VARCHAR(50),

    -- Metadata
    asana_permalink_url TEXT,
    notes TEXT,
    archived BOOLEAN DEFAULT FALSE,

    -- Tracking
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_synced_at TIMESTAMP,

    -- Settings
    settings JSONB DEFAULT '{}'::jsonb,

    INDEX idx_projects_asana_gid (asana_gid),
    INDEX idx_projects_portfolio (portfolio_gid)
);
```

**Purpose**: Maps Asana projects to local state, stores code paths, tracks sync status

### 2. Tasks

Tracks all Asana tasks that Aegis processes.

```sql
CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    asana_gid VARCHAR(50) UNIQUE NOT NULL,
    project_id INTEGER REFERENCES projects(id) ON DELETE CASCADE,

    -- Task Details
    name VARCHAR(500) NOT NULL,
    description TEXT,
    html_notes TEXT,

    -- Status
    completed BOOLEAN DEFAULT FALSE,
    completed_at TIMESTAMP,
    due_on DATE,
    due_at TIMESTAMP,

    -- Assignment
    assignee_gid VARCHAR(50),
    assignee_name VARCHAR(255),
    assigned_to_aegis BOOLEAN DEFAULT FALSE,

    -- Hierarchy
    parent_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,
    num_subtasks INTEGER DEFAULT 0,

    -- Metadata
    asana_permalink_url TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    custom_fields JSONB DEFAULT '{}'::jsonb,

    -- Tracking
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    last_synced_at TIMESTAMP,
    modified_at TIMESTAMP,

    INDEX idx_tasks_asana_gid (asana_gid),
    INDEX idx_tasks_project (project_id),
    INDEX idx_tasks_assigned (assigned_to_aegis, completed),
    INDEX idx_tasks_parent (parent_task_id)
);
```

**Purpose**: Local cache of Asana task state, enables queries without API calls

### 3. Task Executions

Tracks each time Aegis attempts to process a task.

```sql
CREATE TABLE task_executions (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE NOT NULL,

    -- Execution Details
    status VARCHAR(50) NOT NULL, -- 'pending', 'in_progress', 'completed', 'failed', 'blocked'
    agent_type VARCHAR(100),

    -- Timing
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP,
    duration_seconds INTEGER,

    -- Results
    success BOOLEAN,
    error_message TEXT,
    output TEXT,

    -- Resources
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd DECIMAL(10, 6),

    -- Context
    context JSONB DEFAULT '{}'::jsonb,
    metadata JSONB DEFAULT '{}'::jsonb,

    INDEX idx_executions_task (task_id),
    INDEX idx_executions_status (status),
    INDEX idx_executions_started (started_at DESC)
);
```

**Purpose**: Audit trail of all task processing attempts, performance metrics

### 4. Agents

Tracks agent instances and their lifecycle.

```sql
CREATE TABLE agents (
    id SERIAL PRIMARY KEY,

    -- Agent Identity
    agent_type VARCHAR(100) NOT NULL,
    agent_id VARCHAR(100) UNIQUE NOT NULL,

    -- Status
    status VARCHAR(50) NOT NULL, -- 'idle', 'busy', 'stopped', 'error'
    current_task_id INTEGER REFERENCES tasks(id) ON DELETE SET NULL,

    -- Performance
    tasks_completed INTEGER DEFAULT 0,
    tasks_failed INTEGER DEFAULT 0,
    total_execution_time_seconds INTEGER DEFAULT 0,
    total_tokens_used INTEGER DEFAULT 0,
    total_cost_usd DECIMAL(10, 6) DEFAULT 0,

    -- Lifecycle
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    started_at TIMESTAMP,
    stopped_at TIMESTAMP,
    last_active_at TIMESTAMP,

    -- Configuration
    config JSONB DEFAULT '{}'::jsonb,

    INDEX idx_agents_type (agent_type),
    INDEX idx_agents_status (status)
);
```

**Purpose**: Monitor agent health, track performance, enable load balancing

### 5. Agent Events

Detailed event log for debugging and analysis.

```sql
CREATE TABLE agent_events (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER REFERENCES agents(id) ON DELETE CASCADE NOT NULL,
    task_execution_id INTEGER REFERENCES task_executions(id) ON DELETE SET NULL,

    -- Event Details
    event_type VARCHAR(100) NOT NULL, -- 'started', 'completed', 'error', 'api_call', etc.
    message TEXT,
    level VARCHAR(20) DEFAULT 'INFO', -- 'DEBUG', 'INFO', 'WARNING', 'ERROR'

    -- Context
    data JSONB DEFAULT '{}'::jsonb,

    -- Timing
    occurred_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_events_agent (agent_id, occurred_at DESC),
    INDEX idx_events_execution (task_execution_id),
    INDEX idx_events_type (event_type)
);
```

**Purpose**: Detailed logging for debugging, performance analysis, system monitoring

### 6. Comments

Tracks comments/communications on tasks.

```sql
CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    asana_gid VARCHAR(50) UNIQUE NOT NULL,
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE NOT NULL,

    -- Comment Details
    text TEXT NOT NULL,
    created_by_gid VARCHAR(50),
    created_by_name VARCHAR(255),

    -- Metadata
    is_from_aegis BOOLEAN DEFAULT FALSE,
    comment_type VARCHAR(50), -- 'response', 'question', 'status_update', 'error'

    -- Timing
    created_at TIMESTAMP NOT NULL,

    INDEX idx_comments_task (task_id, created_at DESC),
    INDEX idx_comments_asana (asana_gid)
);
```

**Purpose**: Track conversation history, enables context for follow-up tasks

### 7. Prompt Templates

Versioned prompt storage for agent instructions.

```sql
CREATE TABLE prompt_templates (
    id SERIAL PRIMARY KEY,

    -- Template Identity
    name VARCHAR(100) NOT NULL,
    agent_type VARCHAR(100) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,

    -- Content
    system_prompt TEXT NOT NULL,
    user_prompt_template TEXT NOT NULL,

    -- Status
    active BOOLEAN DEFAULT TRUE,

    -- Metadata
    description TEXT,
    tags JSONB DEFAULT '[]'::jsonb,
    variables JSONB DEFAULT '[]'::jsonb, -- List of template variables

    -- Performance Tracking
    usage_count INTEGER DEFAULT 0,
    success_rate DECIMAL(5, 4),
    avg_tokens_used INTEGER,

    -- Versioning
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by VARCHAR(255),

    UNIQUE (name, agent_type, version),
    INDEX idx_prompts_active (agent_type, active)
);
```

**Purpose**: Manage and version control agent prompts, A/B testing, performance tracking

### 8. System State

Singleton table for global system state.

```sql
CREATE TABLE system_state (
    id INTEGER PRIMARY KEY DEFAULT 1,

    -- Orchestrator Status
    orchestrator_status VARCHAR(50) DEFAULT 'stopped', -- 'running', 'stopped', 'paused'
    orchestrator_pid INTEGER,
    orchestrator_started_at TIMESTAMP,

    -- Last Sync Info
    last_portfolio_sync_at TIMESTAMP,
    last_tasks_sync_at TIMESTAMP,

    -- Statistics
    total_tasks_processed INTEGER DEFAULT 0,
    total_tasks_pending INTEGER DEFAULT 0,
    active_agents_count INTEGER DEFAULT 0,

    -- Configuration
    config JSONB DEFAULT '{}'::jsonb,

    -- Metadata
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    CHECK (id = 1) -- Ensure only one row
);
```

**Purpose**: Global state for orchestrator, system-wide metrics

### 9. Webhooks (Future)

Track webhook deliveries and processing.

```sql
CREATE TABLE webhooks (
    id SERIAL PRIMARY KEY,

    -- Webhook Details
    source VARCHAR(50) NOT NULL, -- 'asana'
    event_type VARCHAR(100) NOT NULL,
    resource_gid VARCHAR(50),
    resource_type VARCHAR(50),

    -- Payload
    payload JSONB NOT NULL,

    -- Processing
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    error_message TEXT,

    -- Timing
    received_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_webhooks_processed (processed, received_at),
    INDEX idx_webhooks_resource (resource_type, resource_gid)
);
```

**Purpose**: Handle real-time Asana updates, ensure no events are lost

## Key Relationships

```
projects (1) ←→ (M) tasks
tasks (1) ←→ (M) task_executions
tasks (1) ←→ (M) comments
agents (1) ←→ (M) task_executions
agents (1) ←→ (M) agent_events
task_executions (1) ←→ (M) agent_events
```

## Indexes Strategy

- **Primary Keys**: Auto-incrementing integers for internal relations
- **Unique Constraints**: Asana GIDs to prevent duplicates
- **Foreign Keys**: Maintain referential integrity
- **Composite Indexes**: For common query patterns (status + timestamp)
- **JSONB GIN Indexes**: For metadata/tags searching (future)

## Data Lifecycle

### Retention Policy

- **Tasks**: Keep indefinitely (archive after 1 year)
- **Task Executions**: Keep last 90 days of detailed logs, summarize older
- **Agent Events**: Keep last 30 days detailed, summarize older
- **Comments**: Keep indefinitely
- **Webhooks**: Purge after 7 days if processed

### Archival Strategy

```sql
-- Archive old execution logs to cold storage
CREATE TABLE task_executions_archive (
    LIKE task_executions INCLUDING ALL
);

-- Periodic archival job
INSERT INTO task_executions_archive
SELECT * FROM task_executions
WHERE completed_at < NOW() - INTERVAL '90 days';
```

## Migration Strategy

- Use **Alembic** for schema migrations
- Version control all migrations
- Test migrations on staging before production
- Support rollback for all migrations

## Future Enhancements

### Vector Storage (Phase 3+)

```sql
-- Add pgvector extension
CREATE EXTENSION vector;

-- Store embeddings for semantic search
CREATE TABLE task_embeddings (
    task_id INTEGER PRIMARY KEY REFERENCES tasks(id),
    embedding vector(1536), -- OpenAI ada-002 dimension
    model VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),

    INDEX idx_embedding_vector USING ivfflat (embedding vector_cosine_ops)
);
```

### Memory System (Phase 3+)

```sql
CREATE TABLE agent_memories (
    id SERIAL PRIMARY KEY,
    agent_id INTEGER REFERENCES agents(id),

    -- Memory Content
    memory_type VARCHAR(50), -- 'episodic', 'semantic', 'procedural'
    content TEXT NOT NULL,
    embedding vector(1536),

    -- Metadata
    importance DECIMAL(3, 2), -- 0.0 to 1.0
    last_accessed_at TIMESTAMP,
    access_count INTEGER DEFAULT 0,

    -- Lifecycle
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP,

    INDEX idx_memories_agent (agent_id),
    INDEX idx_memories_type (memory_type),
    INDEX idx_memories_importance (importance DESC)
);
```

## Performance Considerations

- **Connection Pooling**: Use SQLAlchemy pool (min 5, max 20 connections)
- **Query Optimization**: Analyze slow queries, add indexes as needed
- **Bulk Operations**: Use `COPY` or batch inserts for large data loads
- **Partitioning**: Consider table partitioning for agent_events by date
- **Read Replicas**: Add read replicas for reporting queries in production
