# Integration Tests - Setup Guide

## Overview

The integration tests verify the complete end-to-end flow of the Aegis orchestration system, from Asana task creation through agent processing to response posting and database logging.

## Test Coverage

### E2E Flow Tests (`test_e2e.py`)

#### Core Flow Tests (`TestEndToEndFlow`)

1. **Complete Flow Test** (`test_complete_flow_with_mock_agent`)
   - Creates test task in Asana
   - Records task in database
   - Simulates agent processing
   - Posts response to Asana
   - Verifies execution logging

2. **Error Handling** (`test_error_handling_flow`)
   - Simulates agent failures
   - Tests error comment posting
   - Verifies error logging

3. **Task Assignment** (`test_task_assignment_flow`)
   - Tests task status updates
   - Verifies assignment workflow
   - Tests completion flow

4. **Concurrent Processing** (`test_concurrent_task_processing`)
   - Creates multiple tasks
   - Processes them in parallel
   - Verifies all complete successfully

5. **Retry Mechanism** (`test_retry_mechanism`)
   - Tests API retry logic
   - Verifies resilience to transient failures

#### Database Integration Tests (`TestDatabaseIntegration`)

1. **CRUD Operations** (`test_project_crud_operations`)
   - Tests Create, Read, Update, Delete for projects
   - Verifies data persistence

2. **Relationship Management** (`test_task_execution_relationships`)
   - Tests relationships between Task and TaskExecution models
   - Verifies cascade deletes

#### CLI Integration Tests (`TestCLIIntegration`)

1. **Config Command** (`test_config_command`)
   - Tests `aegis config` command
   - Verifies configuration display

2. **Asana Connection Test** (`test_test_asana_command`)
   - Tests `aegis test-asana` command
   - Verifies Asana API connectivity

#### Full Orchestrator Tests (`TestFullOrchestratorFlow`)

**Note**: These tests require `RUN_ORCHESTRATOR_TESTS=1` environment variable.

1. **Task Discovery and Execution** (`test_orchestrator_task_discovery_and_execution`)
   - Tests complete orchestrator workflow
   - Creates task, discovers it, executes it
   - Verifies end-to-end integration

2. **Multiple Project Handling** (`test_orchestrator_handles_multiple_projects`)
   - Tests orchestrator with multiple projects
   - Verifies task isolation between projects

3. **Execution History Tracking** (`test_execution_history_tracking`)
   - Tests tracking of multiple execution attempts
   - Verifies retry history is maintained
   - Tests querying of execution history

#### Live Agent Tests (`TestLiveAgentIntegration`)

**Note**: These tests require `RUN_LIVE_TESTS=1` and cost money to run.

1. **Real Claude Execution** (`test_real_claude_execution`)
   - Tests with real Claude API
   - Posts actual responses to Asana
   - Verifies token usage tracking

## Prerequisites

### Required Services

1. **PostgreSQL Database**
   - Test database separate from production
   - Recommended: `aegis_test` database

2. **Asana Account**
   - Personal Access Token (PAT)
   - Test workspace
   - Dedicated test project

3. **Optional: Anthropic API**
   - Only needed for live agent tests
   - Can run most tests with mocked agents

### Environment Setup

#### 1. Create Test Database

```bash
# Using Docker (recommended)
docker run --name aegis-test-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=aegis_test \
  -p 5433:5432 \
  -d postgres:16

# Or using local PostgreSQL
createdb aegis_test
```

#### 2. Configure Test Environment

Create a `.env.test` file in the project root:

```bash
# Required for all tests
ASANA_ACCESS_TOKEN=your_asana_pat_here
ASANA_WORKSPACE_GID=your_workspace_gid
ASANA_TEST_PROJECT_GID=your_test_project_gid

# Database (use different DB than production)
TEST_DATABASE_URL=postgresql://localhost:5433/aegis_test
TEST_REDIS_URL=redis://localhost:6379/1

# Optional: For live agent tests
ANTHROPIC_API_KEY=your_api_key_here
ANTHROPIC_MODEL=claude-sonnet-4-5-20250929
```

#### 3. Set Up Asana Test Project

1. Create a new project in Asana named "Aegis E2E Tests"
2. Note the project GID from the URL: `https://app.asana.com/0/PROJECT_GID/...`
3. Add this GID to `.env.test` as `ASANA_TEST_PROJECT_GID`
4. Ensure the project is not used for production work

**Important**: The test project should be dedicated to testing. Test tasks will be automatically cleaned up, but it's best to keep this separate from production projects.

## Running Tests

### Install Test Dependencies

```bash
# Install all dependencies including test requirements
pip install -e ".[test]"

# Or with uv
uv pip install -e ".[test]"
```

### Run All Integration Tests

```bash
# Load test environment and run
export $(cat .env.test | xargs)
pytest tests/integration/test_e2e.py -v

# Or run all integration tests
pytest tests/integration/ -v
```

### Run Specific Test Classes

```bash
# Only E2E flow tests
pytest tests/integration/test_e2e.py::TestEndToEndFlow -v

# Only database tests
pytest tests/integration/test_e2e.py::TestDatabaseIntegration -v
```

### Run Specific Test Cases

```bash
# Run single test
pytest tests/integration/test_e2e.py::TestEndToEndFlow::test_complete_flow_with_mock_agent -v

# Run with output
pytest tests/integration/test_e2e.py::TestEndToEndFlow::test_error_handling_flow -v -s
```

### Run Full Orchestrator Tests

```bash
# Enable orchestrator tests
export RUN_ORCHESTRATOR_TESTS=1
export $(cat .env.test | xargs)
pytest tests/integration/test_e2e.py::TestFullOrchestratorFlow -v
```

### Run Live Agent Tests (Optional)

```bash
# Enable live tests (costs money!)
export RUN_LIVE_TESTS=1
export $(cat .env.test | xargs)
pytest tests/integration/test_e2e.py::TestLiveAgentIntegration -v
```

### Run Tests in Parallel

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run with 4 workers
pytest tests/integration/ -v -n 4
```

## Test Markers

Tests are marked for easy filtering:

```bash
# Run only integration tests
pytest -m integration

# Skip slow tests
pytest -m "not slow"

# Run only live tests
pytest -m live
```

## CI/CD Integration

### GitHub Actions

A complete GitHub Actions workflow is provided at `.github/workflows/integration-tests.yml`.

**Features**:
- Runs on push to main/master/develop branches
- Runs on pull requests
- Can be triggered manually via workflow_dispatch
- Sets up PostgreSQL and Redis services
- Runs basic integration tests (excluding live API tests)
- Tests CLI commands
- Cleans up test tasks after completion
- Optional live tests job (requires manual trigger or commit message with `[run-live-tests]`)

**Required GitHub Secrets**:

Add these secrets in your GitHub repository settings (Settings → Secrets and variables → Actions):

- `ASANA_TEST_TOKEN`: Asana PAT for testing
- `ASANA_TEST_WORKSPACE`: Test workspace GID
- `ASANA_TEST_PROJECT`: Test project GID
- `ASANA_TEST_PORTFOLIO`: Test portfolio GID (optional)
- `ANTHROPIC_API_KEY`: API key for Claude (required for live tests)

**Running Specific Test Suites**:

The workflow includes two jobs:
1. **integration-tests**: Runs on every push/PR (basic tests only)
2. **live-tests**: Only runs when:
   - Manually triggered via GitHub Actions UI
   - Commit message contains `[run-live-tests]`

**Example commit to trigger live tests**:
```bash
git commit -m "Add new feature [run-live-tests]"
```

### GitLab CI

Create `.gitlab-ci.yml`:

```yaml
integration-tests:
  stage: test
  image: python:3.11

  services:
    - postgres:16
    - redis:7

  variables:
    POSTGRES_DB: aegis_test
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: postgres
    TEST_DATABASE_URL: postgresql://postgres:postgres@postgres:5432/aegis_test
    TEST_REDIS_URL: redis://redis:6379/1

  before_script:
    - pip install -e ".[test]"

  script:
    - pytest tests/integration/ -v --tb=short

  only:
    - main
    - merge_requests
```

## Troubleshooting

### Test Database Connection Errors

```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# Check connection
psql -h localhost -p 5433 -U postgres -d aegis_test

# Recreate test database
docker stop aegis-test-postgres
docker rm aegis-test-postgres
# Re-run create command from setup
```

### Asana API Rate Limits

If tests fail due to rate limiting:

```python
# Add delays between tests
pytest tests/integration/ --durations=10 -v --maxfail=1
```

### Test Cleanup Issues

If test tasks remain in Asana:

```bash
# Run cleanup script
python scripts/cleanup_test_tasks.py

# Or manually delete tasks starting with "E2E_TEST_"
```

### Database Schema Mismatch

```bash
# Drop and recreate test database
docker exec -it aegis-test-postgres psql -U postgres -c "DROP DATABASE aegis_test;"
docker exec -it aegis-test-postgres psql -U postgres -c "CREATE DATABASE aegis_test;"

# Re-run tests (tables will be created)
pytest tests/integration/ -v
```

## Test Maintenance

### Adding New Tests

1. Follow existing test structure
2. Use provided fixtures for common setup
3. Add cleanup in teardown
4. Mark tests appropriately (`@pytest.mark.integration`)
5. Document test purpose in docstring

### Test Data Management

- All test tasks must start with `E2E_TEST_` prefix
- Test project should be dedicated to testing
- Cleanup is automatic but verify manually periodically
- Don't use production Asana projects

### Performance Considerations

- Tests create real Asana tasks (API calls)
- Database operations are fast
- Consider running in parallel for speed
- Live agent tests are slow and costly

## Best Practices

1. **Isolation**: Each test should be independent
2. **Cleanup**: Always cleanup test data
3. **Idempotency**: Tests should be repeatable
4. **Fast Feedback**: Mock expensive operations when possible
5. **Real Integration**: Use real APIs for critical paths
6. **Clear Assertions**: Test both success and failure cases
7. **Documentation**: Keep this README updated

## Support

For issues or questions:
- Check test output for detailed error messages
- Review Asana test project for created tasks
- Check database for orphaned records
- See main project documentation

## Test Markers

Tests are organized with pytest markers for easy filtering:

- `integration`: All integration tests (default for this directory)
- `live`: Tests that make real API calls and cost money
- `slow`: Tests that take longer to run

Filter tests by marker:
```bash
# Run only integration tests (exclude live tests)
pytest -m "integration and not live"

# Run only slow tests
pytest -m "slow"

# Run everything except live tests
pytest -m "not live"
```

## Test Environment Variables

Summary of environment variables used in tests:

### Required for Basic Tests
- `ASANA_ACCESS_TOKEN`: Asana API token
- `ASANA_WORKSPACE_GID`: Workspace GID
- `ASANA_TEST_PROJECT_GID`: Dedicated test project GID
- `TEST_DATABASE_URL`: Test database connection string

### Optional
- `ASANA_PORTFOLIO_GID`: Portfolio GID (for orchestrator tests)
- `TEST_REDIS_URL`: Redis connection string (default: redis://localhost:6379/1)
- `RUN_LIVE_TESTS`: Set to "1" to enable live API tests
- `RUN_ORCHESTRATOR_TESTS`: Set to "1" to enable full orchestrator tests
- `ANTHROPIC_API_KEY`: Claude API key (for live tests)
- `ANTHROPIC_MODEL`: Model to use (default: claude-sonnet-4-5-20250929)

## Future Improvements

- [ ] Add performance benchmarks
- [ ] Test webhook integration
- [ ] Add load testing
- [ ] Test multi-agent orchestration
- [ ] Add vector database tests
- [ ] Test concurrent orchestrator instances
- [ ] Add integration tests for `aegis do` and `aegis work-on` commands
- [ ] Test real Claude CLI execution (requires Claude CLI installation)
