# Aegis - Initial Task List & Roadmap

## Phase 1: Foundation (MVP)

### 1. Project Setup
- [x] Initialize git repository
- [x] Create design/ folder and documentation
- [ ] Set up Python project structure (pyproject.toml, virtual env)
- [ ] Configure linting and formatting (ruff, black, mypy)
- [ ] Create initial README.md
- [ ] Set up .gitignore for Python projects

### 2. Database Setup & Schema
- [ ] Install PostgreSQL locally (or use Docker)
- [ ] Set up Alembic for migrations
- [ ] Create initial database schema
  - [ ] Projects table
  - [ ] Tasks table
  - [ ] Task executions table
  - [ ] Agents table
  - [ ] Agent events table
  - [ ] Comments table
  - [ ] Prompt templates table
  - [ ] System state table
- [ ] Create SQLAlchemy models
  - [ ] Base model with common fields (created_at, updated_at)
  - [ ] Project model
  - [ ] Task model
  - [ ] TaskExecution model
  - [ ] Agent model
  - [ ] AgentEvent model
  - [ ] Comment model
  - [ ] PromptTemplate model
  - [ ] SystemState model
- [ ] Create database session management
  - [ ] Connection pooling configuration
  - [ ] Session lifecycle (per-request, per-task)
  - [ ] Transaction handling
- [ ] Implement basic CRUD operations
  - [ ] Project CRUD
  - [ ] Task CRUD
  - [ ] TaskExecution CRUD
- [ ] Add database utilities
  - [ ] Sync utility (fetch from Asana → store in DB)
  - [ ] Query helpers for common patterns
- [ ] Write database tests
  - [ ] Model validation tests
  - [ ] CRUD operation tests
  - [ ] Relationship tests
- [ ] Create database seeding script
  - [ ] Seed with existing Asana projects (Triptic, Aegis)
  - [ ] Create sample data for testing

See [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) for complete schema design.

### 3. Asana Integration (Basic)
- [ ] Research Asana API capabilities and authentication methods
- [ ] Create Asana API client wrapper
  - [ ] Authentication (OAuth2 or Personal Access Token)
  - [ ] Fetch tasks from specific projects
  - [ ] Read task details (description, assignee, due date)
  - [ ] Update task status
  - [ ] Add comments to tasks
  - [ ] Handle attachments (upload/download)
- [ ] Create data models for Asana entities (Task, Project, Comment)
- [ ] Implement error handling and rate limiting
- [ ] Write unit tests for Asana client

### 4. Task Parser & Processor
- [ ] Design task instruction parsing strategy
  - [ ] Extract intent from task title
  - [ ] Parse structured information from description
  - [ ] Identify task type (code, research, content, etc.)
- [ ] Build prompt templates for task analysis
- [ ] Implement task context gathering
  - [ ] Related tasks and dependencies
  - [ ] Project context
  - [ ] Attached files and resources
- [ ] Create task validation and sanity checks

### 5. Single Agent Executor (Claude Integration)
- [ ] Set up Anthropic API client
- [ ] Design base agent class/interface
- [ ] Implement simple task executor
  - [ ] Accept parsed task input
  - [ ] Generate appropriate prompts
  - [ ] Execute using Claude API
  - [ ] Handle streaming responses
- [ ] Add retry logic and error handling
- [ ] Track token usage and costs
- [ ] Log agent interactions for debugging

### 6. Response Handler & Communication
- [ ] Format agent output for Asana comments
  - [ ] Markdown formatting
  - [ ] Code blocks and syntax highlighting
  - [ ] Progress updates
- [ ] Implement result posting to Asana
- [ ] Handle multi-part responses (chunking if needed)
- [ ] Add ability to ask clarifying questions via comments
- [ ] Implement status updates (in-progress, completed, blocked)

### 7. Basic Orchestration Loop
- [ ] Create main event loop
- [ ] Implement task polling mechanism
  - [ ] Fetch new assigned tasks
  - [ ] Respect rate limits
  - [ ] Handle polling errors gracefully
- [ ] Add task queue management
- [ ] Implement basic task prioritization
- [ ] Add graceful shutdown handling

### 8. Configuration & Deployment
- [ ] Create configuration system
  - [ ] API keys (Asana, Anthropic)
  - [ ] Target projects/workspaces
  - [ ] Agent parameters
  - [ ] Feature flags
- [ ] Environment variable management (.env)
- [ ] Create deployment scripts
- [ ] Add logging configuration
- [ ] Set up monitoring basics (health checks)

### 9. Testing & Documentation
- [ ] Write integration tests for end-to-end flow
- [ ] Create example Asana tasks for testing
- [ ] Document API key setup process
- [ ] Write operator guide for running Aegis
- [ ] Create troubleshooting guide

## Phase 2: Multi-Agent Orchestration

### 10. Agent Framework
- [ ] Design agent communication protocol
- [ ] Create specialized agent types
  - [ ] Router Agent (task classification)
  - [ ] Planner Agent (task decomposition)
  - [ ] Executor Agent (task completion)
  - [ ] Reviewer Agent (quality check)
  - [ ] Code Agent (software development)
  - [ ] Research Agent (information gathering)
- [ ] Implement agent registry and factory
- [ ] Build inter-agent messaging system
- [ ] Add agent lifecycle management

### 11. Task Decomposition System
- [ ] Design hierarchical task structure
- [ ] Implement task breakdown logic
- [ ] Create subtask generation in Asana
- [ ] Build dependency tracking
- [ ] Add parallel vs sequential execution logic
- [ ] Implement result aggregation

### 12. Prompt Library
- [ ] Create prompt management system
- [ ] Design system prompts for each agent type
- [ ] Build task-specific prompt templates
- [ ] Implement dynamic prompt composition
- [ ] Add prompt versioning
- [ ] Create prompt testing framework

### 13. State Management (Enhanced)
- [ ] Design state persistence strategy
- [ ] Set up PostgreSQL database
  - [ ] Schema for tasks, agents, executions
  - [ ] Migration system
- [ ] Implement task state machine
- [ ] Add checkpoint/resume capability
- [ ] Build state recovery mechanisms

## Phase 3: Intelligence & Knowledge

### 14. Vector Database Integration
- [ ] Evaluate vector DB options (Pinecone, Qdrant, Weaviate)
- [ ] Set up vector database instance
- [ ] Design embedding strategy
  - [ ] What to embed (tasks, results, docs)
  - [ ] Embedding model selection
- [ ] Implement semantic search
- [ ] Build context retrieval system
- [ ] Add relevance ranking

### 15. Memory System
- [ ] Design conversation memory structure
- [ ] Implement short-term memory (current task context)
- [ ] Build long-term memory (historical context)
- [ ] Create memory summarization
- [ ] Add memory retrieval strategies
- [ ] Implement forgetting/pruning logic

### 16. Learning & Feedback
- [ ] Design feedback collection mechanism
- [ ] Implement user feedback parsing (from Asana reactions/comments)
- [ ] Build feedback storage and analysis
- [ ] Create performance metrics tracking
- [ ] Implement prompt refinement based on feedback
- [ ] Add A/B testing for prompt variations

### 17. Advanced Task Features
- [ ] Implement proactive task suggestions
- [ ] Add task estimation capabilities
- [ ] Build automatic dependency detection
- [ ] Create smart task prioritization
- [ ] Implement deadline awareness
- [ ] Add resource constraint handling

## Phase 4: Production & Scale

### 18. Webhook Integration
- [ ] Set up webhook server
- [ ] Implement Asana webhook handlers
- [ ] Add webhook verification
- [ ] Replace polling with real-time updates
- [ ] Handle webhook failures and replay

### 19. Advanced Orchestration
- [ ] Implement dynamic agent scaling
- [ ] Add load balancing across agents
- [ ] Build agent performance monitoring
- [ ] Create intelligent agent selection
- [ ] Add agent specialization training
- [ ] Implement collaborative agent workflows

### 20. Production Infrastructure
- [ ] Containerize application (Docker)
- [ ] Create Kubernetes manifests
- [ ] Set up CI/CD pipeline
- [ ] Implement secrets management
- [ ] Add backup and disaster recovery
- [ ] Create deployment playbooks

### 21. Monitoring & Observability
- [ ] Implement structured logging
- [ ] Set up metrics collection (Prometheus)
- [ ] Create dashboards (Grafana)
- [ ] Add distributed tracing
- [ ] Implement alerting rules
- [ ] Build cost tracking and optimization

### 22. Multi-Tenancy & Scale
- [ ] Add workspace/user isolation
- [ ] Implement resource quotas
- [ ] Build usage billing system
- [ ] Add authentication and authorization
- [ ] Create admin interface
- [ ] Implement rate limiting per user

### 23. Advanced Features
- [ ] Multi-modal support (images, documents)
- [ ] Code execution sandbox
- [ ] External tool integrations (GitHub, Slack, etc.)
- [ ] Custom agent plugin system
- [ ] Web scraping capabilities
- [ ] Data pipeline execution

## Immediate Next Steps (Start Here)

1. **Set up Python project structure** - Get the codebase foundation ready
2. **Create Asana API client** - Core integration for the entire system
3. **Build simple executor** - Prove end-to-end flow works
4. **Test with real task** - Validate the concept with a real Asana task

## Open Questions & Decisions Needed

- [ ] Which vector database to use? (Qdrant for self-hosted vs Pinecone for managed)
- [ ] Hosting strategy: Self-hosted vs cloud? (AWS, GCP, or local initially?)
- [ ] Database: Managed PostgreSQL or self-hosted?
- [ ] Authentication: OAuth2 flow or simpler PAT for MVP?
- [ ] Agent communication: Simple function calls or message queue?
- [ ] Monitoring: Self-hosted stack or use managed services?

## Success Criteria for MVP

- [ ] Can successfully read assigned tasks from a designated Asana project
- [ ] Can parse task intent and generate appropriate responses using Claude
- [ ] Can post responses back as Asana comments
- [ ] Can update task status based on completion
- [ ] Runs reliably in a loop with error handling
- [ ] Has basic logging and monitoring
- [ ] Can handle at least 3 different task types (code, research, simple Q&A)

## Resources & Links

- [Asana API Documentation](https://developers.asana.com/docs)
- [Anthropic API Documentation](https://docs.anthropic.com/)
- [Claude Code Documentation](https://code.claude.com/docs/)
- Vector DB Options:
  - [Qdrant](https://qdrant.tech/)
  - [Pinecone](https://www.pinecone.io/)
  - [Weaviate](https://weaviate.io/)
